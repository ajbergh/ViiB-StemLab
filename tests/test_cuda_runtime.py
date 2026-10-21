from __future__ import annotations

import hashlib
import io
import json
import sys
import threading
import urllib.error
import zipfile
from pathlib import Path

import pytest

from viib_stemlab import cuda_runtime as cuda
from viib_stemlab.engines.demucs import DemucsEngine, TorchRuntimeInfo


class Response(io.BytesIO):
    def geturl(self):
        return "https://releases.example/worker.zip"


@pytest.fixture
def release(tmp_path, monkeypatch):
    archive = io.BytesIO()
    contents = {"stemlab-backend.exe": b"worker", "_internal/torch.dll": b"library"}
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, data in contents.items():
            bundle.writestr(name, data)
    data = archive.getvalue()
    manifest = {"protocol": 1, "platform": "windows-x64", "version": "test-v1",
                "executable": "stemlab-backend.exe", "minimumDriver": "551.78",
                "url": "https://releases.example/worker.zip", "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "unpackedSize": sum(map(len, contents.values()))}
    monkeypatch.setattr(cuda, "probe_nvidia", lambda: {
        "supported": True, "gpus": [{"name": "NVIDIA Test", "driver": "580.1", "memoryMb": 8192}]})
    probes = []
    monkeypatch.setattr(cuda, "probe_worker", lambda executable, **kw: probes.append(executable))
    monkeypatch.setattr(cuda.urllib.request, "urlopen", lambda url, **kw:
                        Response(data if url.endswith(".zip") else json.dumps(manifest).encode()))
    return cuda.CudaRuntimeManager(tmp_path / "runtimes", "https://releases.example/manifest.json"), manifest, probes


def test_install_verify_restart_and_share_model_cache(release, monkeypatch):
    manager, manifest, probes = release
    manager._run(True)
    assert manager.status()["ready"]
    assert manager.worker.read_bytes() == b"worker"
    assert len(probes) == 1
    restarted = cuda.CudaRuntimeManager(manager.root, "")
    restarted._run(False)
    assert restarted.worker == manager.worker
    assert len(probes) == 2
    monkeypatch.setenv("TORCH_HOME", "shared-model-cache")
    assert cuda.worker_environment()["TORCH_HOME"] == "shared-model-cache"
    assert cuda.worker_environment()["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


@pytest.mark.parametrize("field,value", [("sha256", "0" * 64), ("size", 1), ("unpackedSize", 1)])
def test_bad_archive_never_promoted(release, field, value):
    manager, manifest, probes = release
    manifest[field] = value
    manager._run(True)
    assert manager.status()["status"] == "failed"
    assert not (manager.root / "current.json").exists()
    assert not probes
    assert not list(manager.root.glob("cuda-*"))


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/escape", r"a\..\escape", "CON.txt", "a/file."])
def test_unsafe_paths_rejected(name):
    with pytest.raises(ValueError, match="Unsafe"):
        cuda.safe_member(name)


def test_failed_gpu_probe_and_retry(release, monkeypatch):
    manager, _, _ = release
    def fail(_, **kw):
        raise ValueError("Unsupported GPU architecture")
    monkeypatch.setattr(cuda, "probe_worker", fail)
    manager._run(True)
    assert manager.status()["status"] == "failed"
    assert manager.worker is None
    assert not (manager.root / "current.json").exists()
    monkeypatch.setattr(cuda, "probe_worker", lambda _, **kw: {})
    manager._run(True)
    assert manager.worker


@pytest.mark.parametrize("code", [404, 403, 503])
@pytest.mark.parametrize("missing_part", [False, True])
def test_http_failure_preserves_cpu_and_explains_missing_release(release, monkeypatch, code, missing_part):
    manager, _, probes = release
    original = cuda.urllib.request.urlopen

    def fetch(url, **kwargs):
        if not missing_part or url.endswith(".zip"):
            raise urllib.error.HTTPError(url, code, "Download unavailable", {}, None)
        return original(url, **kwargs)

    monkeypatch.setattr(cuda.urllib.request, "urlopen", fetch)
    manager._run(True)
    state = manager.status()
    assert state["status"] == "failed"
    assert not state["ready"]
    assert "CPU processing remains available" in state["message"]
    assert ("publisher must publish" in state["message"]) == (code == 404)
    assert not probes
    assert not (manager.root / "current.json").exists()
    assert not list(manager.root.glob("cuda-*"))


def test_corrupt_installed_worker_not_used_offline(release):
    manager, _, _ = release
    manager._run(True)
    manager.worker.write_bytes(b"corrupt")
    restarted = cuda.CudaRuntimeManager(manager.root, "")
    restarted._run(False)
    assert restarted.worker is None
    assert not restarted.status()["ready"]


def test_malformed_receipt_can_be_repaired(release):
    manager, _, _ = release
    manager.root.mkdir()
    (manager.root / "current.json").write_text("[]")
    manager._run(True)
    assert manager.worker


def test_cancellation_cleans_stage(release, monkeypatch):
    manager, _, probes = release
    original = cuda.urllib.request.urlopen
    def download(url, **kwargs):
        response = original(url, **kwargs)
        if url.endswith(".zip"):
            manager.cancel()
        return response
    monkeypatch.setattr(cuda.urllib.request, "urlopen", download)
    manager._run(True)
    assert manager.status()["status"] == "cancelled"
    assert not (manager.root / "current.json").exists()
    assert not probes


def test_no_download_when_disabled_unconfigured_or_unsupported(release, monkeypatch):
    manager, _, _ = release
    monkeypatch.setattr(cuda.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("Unexpected network"))
    manager._run(False)
    assert manager.status()["status"] == "available"
    manager.manifest_url = ""
    manager._run(True)
    assert manager.status()["status"] == "not_configured"
    monkeypatch.setattr(cuda, "probe_nvidia", lambda: {"supported": False, "gpus": [], "message": "No driver"})
    manager._run(True)
    assert manager.status()["status"] == "unsupported"


def test_incompatible_driver_prevents_download(release):
    manager, manifest, probes = release
    manifest["minimumDriver"] = "999.0"
    manager._run(True)
    assert manager.status()["status"] == "incompatible"
    assert not probes


def test_cpu_backend_selects_cuda_sidecar(release, monkeypatch):
    manager, _, _ = release
    manager._run(True)
    monkeypatch.setattr(cuda, "get_cuda_worker", lambda: manager.worker)
    monkeypatch.setattr("viib_stemlab.engines.demucs.importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr("viib_stemlab.engines.demucs.probe_torch_runtime", lambda:
                        TorchRuntimeInfo(True, "2.6.0+cpu", False, None, False))
    engine = DemucsEngine()
    assert engine.capabilities().auto_device == "cuda"
    assert engine.worker_command("cuda") == [str(manager.worker), "--demucs-worker"]
    assert str(manager.worker) not in engine.worker_command("cpu")


def test_manifest_rejects_protocol_and_insecure_url(release):
    _, manifest, _ = release
    for invalid in ({"protocol": 2}, {"url": "http://example/worker.zip"}, {"sha256": "prefix"}):
        with pytest.raises(ValueError):
            cuda.validate_manifest(manifest | invalid)


def test_multipart_download_and_part_integrity(release, monkeypatch):
    manager, manifest, _ = release
    original = cuda.urllib.request.urlopen
    data = original(manifest["url"]).read()
    chunks = [data[:50], data[50:]]
    manifest["parts"] = [{"url": f"https://releases.example/part{i}", "size": len(chunk),
                          "sha256": hashlib.sha256(chunk).hexdigest()} for i, chunk in enumerate(chunks)]
    responses = {part["url"]: chunk for part, chunk in zip(manifest["parts"], chunks, strict=True)}
    monkeypatch.setattr(cuda.urllib.request, "urlopen", lambda url, **kw:
                        Response(responses[url]) if url in responses else original(url, **kw))
    manager._run(True)
    assert manager.worker
    manager2 = cuda.CudaRuntimeManager(manager.root / "second", manager.manifest_url)
    responses[manifest["parts"][1]["url"]] = b"corrupt"
    manager2._run(True)
    assert manager2.worker is None
    assert manager2.status()["status"] == "failed"


def test_installed_parent_junction_is_rejected(release, monkeypatch):
    manager, manifest, _ = release
    manager._run(True)
    directory = manager.root / manifest["version"]
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda p: p == directory or original(p))
    monkeypatch.setattr(cuda, "probe_worker", lambda *a, **kw: pytest.fail("Linked worker executed"))
    with pytest.raises(ValueError, match="links or junctions"):
        manager._installed()


def test_probe_cancellation_stops_child_process(tmp_path):
    # Use a real sleeping process to exercise communicate/kill and pipe cleanup.
    event = threading.Event()
    process = cuda.subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                   stdout=cuda.subprocess.PIPE, stderr=cuda.subprocess.PIPE, text=True)
    from unittest.mock import patch
    event.set()
    with patch.object(cuda, "spawn_worker", return_value=process), pytest.raises(InterruptedError):
        cuda.probe_worker(tmp_path / "worker.exe", cancel=event)
    assert process.poll() is not None
