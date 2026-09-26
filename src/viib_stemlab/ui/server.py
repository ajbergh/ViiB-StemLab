"""Lightweight, zero-dependency HTTP API and static file server for ViiB-StemLab Desktop UI."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from viib_stemlab.constants import DEFAULT_MODEL
from viib_stemlab.doctor import get_doctor_report
from viib_stemlab.models import ModelCacheManager
from viib_stemlab.package import validate_package
from viib_stemlab.queue.discovery import ingest_paths
from viib_stemlab.queue.models import JobStatus
from viib_stemlab.queue.runner import QueueRunner
from viib_stemlab.queue.store import QueueStore

logger = logging.getLogger("viib_stemlab.ui")


class StemLabRequestHandler(BaseHTTPRequestHandler):
    """Handles REST API requests and serves desktop UI static assets."""

    server: StemLabHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard BaseHTTPRequestHandler stderr noise in favor of logging."""
        logger.debug("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)

    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        content = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def _send_error(self, message: str, status: int = HTTPStatus.BAD_REQUEST, error_code: str = "bad_request") -> None:
        self._send_json({"error": message, "error_code": error_code}, status=status)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        path = url.path.rstrip("/")
        query = urllib.parse.parse_qs(url.query)

        if path == "/api/health":
            self._send_json({"status": "ok", "version": "0.1.0"})
            return

        if path == "/api/queue":
            status_filter = query.get("status", [None])[0]
            jobs = self.server.store.list_jobs(status=status_filter)
            counts = {
                "total": self.server.store.count_jobs(),
                "queued": self.server.store.count_jobs(JobStatus.QUEUED),
                "active": sum(
                    self.server.store.count_jobs(s)
                    for s in (
                        JobStatus.PREPARING,
                        JobStatus.SEPARATING,
                        JobStatus.PACKAGING,
                        JobStatus.VALIDATING,
                        JobStatus.FINALIZING,
                    )
                ),
                "complete": self.server.store.count_jobs(JobStatus.COMPLETE),
                "failed": self.server.store.count_jobs(JobStatus.FAILED),
                "cancelled": self.server.store.count_jobs(JobStatus.CANCELLED),
            }
            self._send_json({
                "jobs": [j.to_dict() for j in jobs],
                "counts": counts,
                "is_running": self.server.runner.is_running,
                "active_job_id": self.server.runner.active_job_id,
            })
            return

        if path == "/api/doctor":
            doc = get_doctor_report()
            self._send_json(doc)
            return

        if path == "/api/models":
            mgr = ModelCacheManager()
            models = mgr.list_known_models()
            self._send_json({
                "cache_dir": str(mgr.cache_dir),
                "models": [
                    {
                        "name": m.name,
                        "signature": m.signature,
                        "filename": m.filename,
                        "cached": m.cached,
                        "size_bytes": m.size_bytes,
                        "expected_size_bytes": m.expected_size_bytes,
                        "is_default": m.name == DEFAULT_MODEL,
                    }
                    for m in models
                ],
            })
            return

        if path == "/api/library":
            output_dir = query.get("path", [self.server.default_library_path])[0]
            packages = self._scan_library(output_dir)
            self._send_json({"library_path": output_dir, "packages": packages})
            return

        # Serve static UI files if configured
        if self.server.static_dir and self.server.static_dir.is_dir():
            self._serve_static(path)
            return

        self._send_error("Not found", status=HTTPStatus.NOT_FOUND, error_code="not_found")

    def do_POST(self) -> None:
        url = urllib.parse.urlparse(self.path)
        path = url.path.rstrip("/")

        body: dict[str, Any] = {}
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            raw = self.rfile.read(content_length).decode("utf-8")
            try:
                body = json.loads(raw)
            except Exception:
                self._send_error("Invalid JSON body", status=HTTPStatus.BAD_REQUEST)
                return

        if path == "/api/queue/add":
            paths = body.get("paths", [])
            if not paths:
                self._send_error("No paths provided", status=HTTPStatus.BAD_REQUEST)
                return

            output_lib = body.get("output_library", self.server.default_library_path)
            model = body.get("model", DEFAULT_MODEL)
            device = body.get("device", "auto")
            fallback_to_cpu = body.get("fallback_to_cpu", True)
            overwrite = body.get("overwrite", False)
            recursive = body.get("recursive", True)

            result = ingest_paths(
                paths,
                store=self.server.store,
                output_library=output_lib,
                model=model,
                device=device,
                fallback_to_cpu=fallback_to_cpu,
                overwrite=overwrite,
                recursive=recursive,
            )

            self._send_json({
                "added": [j.to_dict() for j in result.added],
                "added_count": len(result.added),
                "skipped_duplicate_queue": [str(p) for p in result.skipped_duplicate_queue],
                "skipped_existing_package": [str(p) for p in result.skipped_existing_package],
                "invalid_files": [str(p) for p in result.invalid_files],
            })
            return

        if path == "/api/queue/start":
            if not self.server.runner.is_running:
                self.server.runner.start_background_worker(recover_orphans=True)
            self._send_json({"status": "started", "is_running": True})
            return

        if path == "/api/queue/stop":
            cancel_active = body.get("cancel_active", False)
            self.server.runner.stop_background_worker(cancel_active=cancel_active, timeout=2.0)
            self._send_json({"status": "stopped", "is_running": self.server.runner.is_running})
            return

        if path == "/api/queue/cancel":
            job_id = body.get("job_id")
            if not job_id:
                self._send_error("job_id is required")
                return
            reason = body.get("reason", "Cancelled by user via UI")
            cancelled = self.server.runner.cancel_job(job_id, reason=reason)
            self._send_json({"job_id": job_id, "cancelled": cancelled})
            return

        if path == "/api/queue/retry":
            job_id = body.get("job_id")
            if not job_id:
                self._send_error("job_id is required")
                return
            retried = self.server.store.retry_job(job_id)
            if retried:
                self._send_json({"job": retried.to_dict()})
            else:
                self._send_error("Job not found or not in failed/cancelled state", status=HTTPStatus.NOT_FOUND)
            return

        if path == "/api/queue/remove":
            job_id = body.get("job_id")
            if not job_id:
                self._send_error("job_id is required")
                return
            deleted = self.server.store.delete_job(job_id)
            self._send_json({"job_id": job_id, "deleted": deleted})
            return

        if path == "/api/queue/clear":
            status_filter = body.get("status")
            cleared_count = self.server.store.clear_jobs(status=status_filter)
            self._send_json({"cleared_count": cleared_count})
            return

        if path == "/api/package/validate":
            pkg_path = body.get("package_path")
            if not pkg_path or not Path(pkg_path).exists():
                self._send_error("Valid package_path is required")
                return
            source_path = body.get("source_path")
            src_obj = Path(source_path) if source_path else None
            try:
                manifest = validate_package(Path(pkg_path), source_path=src_obj)
                self._send_json({"valid": True, "package_id": manifest.packageId})
            except Exception as exc:
                self._send_json({"valid": False, "error": str(exc)})
            return

        if path == "/api/models/download":
            model_name = body.get("model", DEFAULT_MODEL)
            mgr = ModelCacheManager()

            # Execute download in worker thread to prevent blocking HTTP server
            def _download_task() -> None:
                try:
                    mgr.download_model(model_name)
                except Exception as e:
                    logger.error("Async download of %s failed: %s", model_name, e)

            threading.Thread(target=_download_task, daemon=True).start()
            self._send_json({"status": "downloading", "model": model_name})
            return

        self._send_error("Not found", status=HTTPStatus.NOT_FOUND)

    def _serve_static(self, rel_path: str) -> None:
        assert self.server.static_dir is not None
        safe_rel = rel_path.lstrip("/")
        if not safe_rel:
            safe_rel = "index.html"

        target = (self.server.static_dir / safe_rel).resolve()
        # Prevent path traversal outside static_dir
        if not str(target).startswith(str(self.server.static_dir.resolve())):
            self._send_error("Forbidden", status=HTTPStatus.FORBIDDEN)
            return

        # Single-page application fallback: if file does not exist, serve index.html
        if not target.is_file():
            target = self.server.static_dir / "index.html"

        if not target.is_file():
            self._send_error("Not found", status=HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(str(target))
        if not content_type:
            content_type = "application/octet-stream"

        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def _scan_library(self, library_path: str) -> list[dict[str, Any]]:
        lib_path = Path(library_path).resolve()
        if not lib_path.is_dir():
            return []

        packages: list[dict[str, Any]] = []
        try:
            for item in sorted(lib_path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if item.is_dir() and item.suffix == ".viibstems":
                    manifest_file = item / "manifest.json"
                    if manifest_file.is_file():
                        try:
                            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                            stems = [s.stem for s in item.glob("*.wav")]
                            packages.append({
                                "path": str(item),
                                "folder_name": item.name,
                                "package_id": manifest_data.get("packageId"),
                                "created_at": manifest_data.get("createdAt"),
                                "source": manifest_data.get("source"),
                                "model": manifest_data.get("model"),
                                "audio": manifest_data.get("audio"),
                                "stems": stems,
                                "size_bytes": sum(f.stat().st_size for f in item.glob("*")),
                            })
                        except Exception:
                            pass
        except Exception as exc:
            logger.warning("Error scanning library %s: %s", library_path, exc)

        return packages


class StemLabHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server carrying shared QueueStore and QueueRunner references."""

    def __init__(
        self,
        server_address: tuple[str, int],
        store: QueueStore,
        runner: QueueRunner,
        *,
        static_dir: Path | str | None = None,
        default_library_path: str | None = None,
    ) -> None:
        super().__init__(server_address, StemLabRequestHandler)
        self.store = store
        self.runner = runner
        self.static_dir = Path(static_dir).resolve() if static_dir else None
        self.default_library_path = default_library_path or os.environ.get(
            "VIIB_STEMLAB_LIBRARY", str(Path.home() / "Music" / "ViiB Stems")
        )
