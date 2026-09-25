from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

from viib_stemlab.queue.models import JobStatus
from viib_stemlab.queue.runner import QueueRunner
from viib_stemlab.queue.store import QueueStore
from viib_stemlab.ui.server import StemLabHTTPServer


def _request_json(url: str, data: dict | None = None, method: str = "GET") -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"} if data is not None else {}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_ui_server_lifecycle_and_endpoints(tmp_path: Path) -> None:
    db_file = tmp_path / "test_ui.db"
    store = QueueStore(db_file)
    runner = QueueRunner(store)

    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html><body>StemLab UI</body></html>", encoding="utf-8")

    server = StemLabHTTPServer(
        ("127.0.0.1", 0),  # port 0 chooses an ephemeral port
        store=store,
        runner=runner,
        static_dir=static_dir,
        default_library_path=str(tmp_path / "stems"),
    )
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # 1. Health
        status, health = _request_json(f"{base_url}/api/health")
        assert status == 200
        assert health["status"] == "ok"
        assert health["version"] == "0.1.0"

        # 2. Queue empty
        status, q = _request_json(f"{base_url}/api/queue")
        assert status == 200
        assert q["jobs"] == []
        assert q["counts"]["total"] == 0

        # 3. Add audio file to queue
        audio = tmp_path / "test.flac"
        audio.write_bytes(b"dummy flac data")
        status, added = _request_json(
            f"{base_url}/api/queue/add",
            data={"paths": [str(audio)], "output_library": str(tmp_path / "stems")},
            method="POST",
        )
        assert status == 200
        assert added["added_count"] == 1
        job_id = added["added"][0]["id"]

        # 4. Queue not empty
        status, q = _request_json(f"{base_url}/api/queue")
        assert status == 200
        assert len(q["jobs"]) == 1
        assert q["counts"]["total"] == 1
        assert q["counts"]["queued"] == 1

        # 5. Cancel queued job
        status, cancel_resp = _request_json(
            f"{base_url}/api/queue/cancel",
            data={"job_id": job_id, "reason": "Test cancel"},
            method="POST",
        )
        assert status == 200
        assert cancel_resp["job_id"] == job_id

        # Check job is cancelled
        j = store.get_job(job_id)
        assert j is not None
        assert j.status == JobStatus.CANCELLED

        # 6. Retry job
        status, retry_resp = _request_json(
            f"{base_url}/api/queue/retry",
            data={"job_id": job_id},
            method="POST",
        )
        assert status == 200
        assert retry_resp["job"]["status"] == "queued"

        # 7. Start and stop queue runner
        status, start_resp = _request_json(f"{base_url}/api/queue/start", data={}, method="POST")
        assert status == 200
        assert start_resp["status"] == "started"

        status, stop_resp = _request_json(f"{base_url}/api/queue/stop", data={}, method="POST")
        assert status == 200
        assert stop_resp["status"] == "stopped"

        # 8. Doctor endpoint
        status, doc = _request_json(f"{base_url}/api/doctor")
        assert status == 200
        assert "python" in doc
        assert "demucs" in doc

        # 9. Models endpoint
        status, models_resp = _request_json(f"{base_url}/api/models")
        assert status == 200
        assert "models" in models_resp
        assert len(models_resp["models"]) > 0

        # 10. Library endpoint
        status, lib_resp = _request_json(f"{base_url}/api/library")
        assert status == 200
        assert "packages" in lib_resp

        # 11. Clear jobs
        status, clear_resp = _request_json(
            f"{base_url}/api/queue/clear",
            data={},
            method="POST",
        )
        assert status == 200

        # 12. Static file serving
        with urllib.request.urlopen(f"{base_url}/") as resp:
            content = resp.read().decode("utf-8")
            assert "StemLab UI" in content

    finally:
        server.shutdown()
        server.server_close()


def test_ui_server_error_cases(tmp_path: Path) -> None:
    db_file = tmp_path / "test_err.db"
    store = QueueStore(db_file)
    runner = QueueRunner(store)

    server = StemLabHTTPServer(
        ("127.0.0.1", 0),
        store=store,
        runner=runner,
    )
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # Invalid path
        status, resp = _request_json(f"{base_url}/api/unknown")
        assert status == 404

        # Add without paths
        status, resp = _request_json(f"{base_url}/api/queue/add", data={}, method="POST")
        assert status == 400
        assert "No paths provided" in resp["error"]

        # Cancel without job_id
        status, resp = _request_json(f"{base_url}/api/queue/cancel", data={}, method="POST")
        assert status == 400

        # Retry non-existent
        status, resp = _request_json(f"{base_url}/api/queue/retry", data={"job_id": "nonexistent"}, method="POST")
        assert status == 404

        # Remove job
        audio = tmp_path / "track.wav"
        audio.touch()
        j = store.add_job(audio, tmp_path / "out")
        status, resp = _request_json(f"{base_url}/api/queue/remove", data={"job_id": j.id}, method="POST")
        assert status == 200
        assert resp["deleted"] is True
        assert store.get_job(j.id) is None

        # Validate non-existent package
        status, resp = _request_json(f"{base_url}/api/package/validate", data={"package_path": str(tmp_path / "fake.viibstems")}, method="POST")
        assert status == 400

    finally:
        server.shutdown()
        server.server_close()


def test_ui_server_serves_desktop_dist(tmp_path: Path) -> None:
    repo_dist = Path(__file__).resolve().parent.parent / "desktop" / "dist"
    if not repo_dist.is_dir():
        return

    db_file = tmp_path / "test_dist.db"
    store = QueueStore(db_file)
    runner = QueueRunner(store)

    server = StemLabHTTPServer(
        ("127.0.0.1", 0),
        store=store,
        runner=runner,
        static_dir=repo_dist,
    )
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        with urllib.request.urlopen(f"{base_url}/") as resp:
            content = resp.read().decode("utf-8")
            assert "ViiB StemLab" in content
            assert resp.headers.get_content_type() == "text/html"
    finally:
        server.shutdown()
        server.server_close()
