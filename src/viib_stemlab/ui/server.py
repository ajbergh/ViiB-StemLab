"""Lightweight, zero-dependency HTTP API and static file server for ViiB-StemLab Desktop UI."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import secrets
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from viib_stemlab import __version__
from viib_stemlab.constants import DEFAULT_MODEL
from viib_stemlab.cuda_runtime import get_cuda_manager
from viib_stemlab.doctor import get_doctor_report
from viib_stemlab.models import ModelCacheManager
from viib_stemlab.package import validate_package
from viib_stemlab.queue.discovery import ingest_paths
from viib_stemlab.queue.models import JobStatus
from viib_stemlab.queue.runner import QueueRunner
from viib_stemlab.queue.store import QueueStore
from viib_stemlab.ui.settings import SettingsStore

logger = logging.getLogger("viib_stemlab.ui")


class StemLabRequestHandler(BaseHTTPRequestHandler):
    """Handles REST API requests and serves desktop UI static assets."""

    server: StemLabHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard BaseHTTPRequestHandler stderr noise in favor of logging."""
        logger.debug("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)

    def _set_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in self.server.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _authorized(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and origin not in self.server.allowed_origins:
            self._send_error("Origin is not allowed", HTTPStatus.FORBIDDEN)
            return False
        if self.server.session_token and not secrets.compare_digest(
            self.headers.get("Authorization", ""), f"Bearer {self.server.session_token}"
        ):
            self._send_error("Desktop session required", HTTPStatus.UNAUTHORIZED)
            return False
        return True

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

        if path.startswith("/api/") and not self._authorized():
            return

        if path == "/api/settings":
            self._send_json(self.server.settings.get())
            return

        if path == "/api/cuda":
            self._send_json(self.server.cuda.status() | {"automatic": self.server.settings.get()["auto_cuda"]})
            return

        if path == "/api/health":
            self._send_json({"status": "ok", "version": __version__})
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
                "downloads": self.server.download_status(),
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
            output_dir = query.get("path", [self.server.settings.get()["library_path"]])[0]
            packages = self._scan_library(output_dir)
            self._send_json({"library_path": output_dir, "packages": packages})
            return

        # Serve static UI files if configured
        if self.server.static_dir and self.server.static_dir.is_dir():
            self._serve_static(path)
            return

        self._send_error("Not found", status=HTTPStatus.NOT_FOUND, error_code="not_found")

    def do_POST(self) -> None:
        if not self._authorized():
            return
        url = urllib.parse.urlparse(self.path)
        path = url.path.rstrip("/")

        body: dict[str, Any] = {}
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_error("Invalid Content-Length")
            return
        if content_length < 0 or content_length > 1048576:
            self._send_error("Request body too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        if content_length > 0:
            try:
                raw = self.rfile.read(content_length).decode("utf-8")
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
            except Exception:
                self._send_error("Invalid JSON body", status=HTTPStatus.BAD_REQUEST)
                return

        if path == "/api/settings":
            try:
                values = self.server.settings.update(body)
                if "auto_cuda" in body or "device" in body:
                    if not values["auto_cuda"] or values["device"] not in ("auto", "cuda"):
                        self.server.cuda.cancel()
                    else:
                        self.server.prepare_cuda()
                self._send_json(values)
            except (ValueError, OSError) as exc:
                self._send_error(str(exc))
            return

        if path == "/api/cuda/install":
            self.server.cuda.start()
            self._send_json(self.server.cuda.status())
            return

        if path == "/api/cuda/cancel":
            self.server.settings.update({"auto_cuda": False})
            self.server.cuda.cancel()
            self._send_json(self.server.cuda.status())
            return

        if path == "/api/queue/add":
            paths = body.get("paths", [])
            if not paths:
                self._send_error("No paths provided", status=HTTPStatus.BAD_REQUEST)
                return

            preferences = self.server.settings.get()
            output_lib = body.get("output_library") or preferences["library_path"]
            model = body.get("model", preferences["model"])
            device = body.get("device", preferences["device"])
            fallback_to_cpu = body.get("fallback_to_cpu", preferences["fallback_to_cpu"])
            if model != DEFAULT_MODEL:
                self._send_error("Only htdemucs_6s supports six-stem packages")
                return
            output_format = body.get("output_format", preferences["output_format"])
            if output_format not in ("wav", "ogg", "mp3"):
                self._send_error("Choose wav, ogg, or mp3 for output_format")
                return
            overwrite = body.get("overwrite", False)
            recursive = body.get("recursive", True)

            result = ingest_paths(
                paths,
                store=self.server.store,
                output_library=output_lib,
                model=model,
                device=device,
                fallback_to_cpu=fallback_to_cpu,
                output_format=output_format,
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
            if model_name != DEFAULT_MODEL:
                self._send_error("Unknown or unsupported model")
                return
            self.server.start_download(model_name)
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
        if not target.is_relative_to(self.server.static_dir.resolve()):
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
                            stems = [s.stem for s in (p for p in item.iterdir() if p.suffix.lower() in (".wav", ".wave", ".ogg", ".mp3"))]
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
        session_token: str | None = None,
    ) -> None:
        super().__init__(server_address, StemLabRequestHandler)
        self.store = store
        self.runner = runner
        self.static_dir = Path(static_dir).resolve() if static_dir else None
        self.default_library_path = default_library_path or os.environ.get(
            "VIIB_STEMLAB_LIBRARY", str(Path.home() / "Music" / "ViiB Stems")
        )
        self.session_token = session_token
        self.allowed_origins = {
            "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
            "http://127.0.0.1:5173", f"http://127.0.0.1:{self.server_port}",
            f"http://localhost:{self.server_port}",
        }
        self.settings = SettingsStore(store.db_path.parent / "settings.json", self.default_library_path)
        self.cuda = get_cuda_manager()
        self._download_lock = threading.Lock()
        self._downloads: dict[str, dict[str, Any]] = {}

    def prepare_cuda(self) -> None:
        preferences = self.settings.get()
        self.cuda.start(download=preferences["auto_cuda"] and preferences["device"] in ("auto", "cuda"))

    def download_status(self) -> dict[str, Any]:
        with self._download_lock:
            return {name: dict(state) for name, state in self._downloads.items()}

    def start_download(self, model: str) -> None:
        with self._download_lock:
            if self._downloads.get(model, {}).get("status") == "downloading":
                return
            self._downloads[model] = {"status": "downloading", "progress": 0, "message": "Starting download"}

        def update(progress: Any) -> None:
            with self._download_lock:
                self._downloads[model].update(progress=progress.progress, message=progress.message)

        def download() -> None:
            try:
                ModelCacheManager().download_model(model, progress=update)
                with self._download_lock:
                    self._downloads[model].update(status="complete", progress=1, message="Ready for offline use")
            except Exception as exc:
                logger.exception("Model download failed")
                with self._download_lock:
                    self._downloads[model].update(status="failed", message=str(exc))

        threading.Thread(target=download, daemon=True, name="ModelDownload").start()
