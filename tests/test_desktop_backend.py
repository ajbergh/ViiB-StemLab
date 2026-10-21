from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

from viib_stemlab.engines.demucs import demucs_command
from viib_stemlab.progress import ProgressUpdate
from viib_stemlab.queue.runner import QueueRunner
from viib_stemlab.queue.store import QueueStore
from viib_stemlab.ui.server import StemLabHTTPServer
from viib_stemlab.ui.settings import SettingsStore


@contextmanager
def running_server(tmp_path: Path):
    store = QueueStore(tmp_path / "queue.db")
    server = StemLabHTTPServer(("127.0.0.1", 0), store, QueueRunner(store), session_token="secret")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def request(server, path, data=None, token="secret", origin=None):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}", headers=headers,
                                 data=json.dumps(data).encode() if data is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.load(error), error.headers


def test_private_api_rejects_foreign_origins_and_wrong_tokens(tmp_path):
    with running_server(tmp_path) as server:
        assert request(server, "/api/health", token="wrong")[0] == 401
        assert request(server, "/api/queue/add", {"paths": ["/tmp/a.wav"]}, token="")[0] == 401
        status, _, headers = request(server, "/api/health", origin="https://untrusted.example")
        assert status == 403
        assert headers.get("Access-Control-Allow-Origin") is None
        status, _, headers = request(server, "/api/health", origin="http://tauri.localhost")
        assert status == 200
        assert headers["Access-Control-Allow-Origin"] == "http://tauri.localhost"


def test_preferences_survive_restart_and_queue_uses_them(tmp_path):
    library = str(tmp_path / "Chosen Library")
    audio = tmp_path / "track.flac"
    audio.write_bytes(b"fixture")
    with running_server(tmp_path) as server:
        assert request(server, "/api/settings", {"library_path": library, "device": "cpu"})[0] == 200
        assert request(server, "/api/settings", {"model": "htdemucs"})[0] == 400
        assert request(server, "/api/queue/add", {"paths": [str(audio)], "model": "htdemucs"})[0] == 400
    with running_server(tmp_path) as server:
        prefs = request(server, "/api/settings")[1]
        assert prefs["library_path"] == library
        assert prefs["device"] == "cpu"
        status, result, _ = request(server, "/api/queue/add", {"paths": [str(audio)]})
        assert status == 200
        assert result["added"][0]["output_library"] == library
        assert result["added"][0]["device"] == "cpu"


def test_invalid_settings_do_not_overwrite_existing_file(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", str(tmp_path))
    store.update({"device": "cpu"})
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.update({"fallback_to_cpu": "false"})
    assert store.path.read_bytes() == before


def test_model_download_progress_failure_retry_and_duplicate_suppression(tmp_path, monkeypatch):
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def download(self, name, *, progress):
        calls.append(name)
        progress(ProgressUpdate("preflight", 0.5, "Half downloaded"))
        entered.set()
        assert release.wait(timeout=5)
        if len(calls) == 1:
            raise OSError("Network disconnected")
        done.set()

    monkeypatch.setattr("viib_stemlab.ui.server.ModelCacheManager.download_model", download)
    with running_server(tmp_path) as server:
        server.start_download("htdemucs_6s")
        assert entered.wait(timeout=5)
        server.start_download("htdemucs_6s")
        assert len(calls) == 1
        assert server.download_status()["htdemucs_6s"]["progress"] == 0.5
        release.set()
        # Wait for the registry's terminal state, with a bounded event-based wait.
        for _ in range(100):
            if server.download_status()["htdemucs_6s"]["status"] == "failed":
                break
            threading.Event().wait(0.01)
        assert server.download_status()["htdemucs_6s"]["message"] == "Network disconnected"
        server.start_download("htdemucs_6s")
        assert done.wait(timeout=5)
        assert len(calls) == 2


def test_frozen_demucs_dispatches_internal_worker(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert demucs_command() == [sys.executable, "--demucs-worker"]


def test_backend_handshake_and_launcher_eof_shutdown(tmp_path):
    env = dict(os.environ, VIIB_STEMLAB_HOME=str(tmp_path))
    env.pop("VIIB_STEMLAB_QUEUE_DB", None)
    process = subprocess.Popen([sys.executable, "-m", "viib_stemlab.desktop_backend"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env)
    try:
        lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        connection = json.loads(lines.get(timeout=20))
        assert connection["url"].startswith("http://127.0.0.1:")
        assert len(connection["token"]) >= 32
        req = urllib.request.Request(connection["url"] + "/api/health",
                                     headers={"Authorization": f"Bearer {connection['token']}"})
        with urllib.request.urlopen(req, timeout=5) as response:
            assert json.load(response)["status"] == "ok"
        process.stdin.close()
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
