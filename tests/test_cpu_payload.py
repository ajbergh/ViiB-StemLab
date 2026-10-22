from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("prepare_cpu_payload", Path(__file__).resolve().parents[1] / "packaging/prepare_cpu_payload.py")
payload_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(payload_builder)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    (root / "notices").mkdir(parents=True)
    (root / "stemlab-backend.exe").write_bytes(b"cpu-exe")
    (root / "notices/python-environment.json").write_text(json.dumps([{"name": "torch", "version": "2.6.0+cpu"}]))
    model = tmp_path / "model.th"
    model.write_bytes(b"test weights")
    monkeypatch.setattr(payload_builder, "MODEL_SHA256", hashlib.sha256(model.read_bytes()).hexdigest())
    monkeypatch.setitem(payload_builder.KNOWN_MODELS["htdemucs_6s"], "expected_size_bytes", model.stat().st_size)
    return root, model


def test_full_payload_inventories_model_and_archive(runtime, tmp_path):
    root, model = runtime
    payload = payload_builder.prepare(root, model)
    assert payload["model"] in payload["files"]
    assert "stemlab-backend.exe" in payload["files"]
    assert "notices/MODEL_NOTICES.md" in payload["files"]
    output = tmp_path / "assets"
    payload_builder.archive_payload(root, output, payload)
    release = json.loads((output / "windows-cpu.json").read_text())
    archive = next(output.glob("*.zip"))
    assert release["size"] == archive.stat().st_size
    assert release["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert release["version"] == payload["version"]
    assert not list(output.glob("*.partial"))


def test_rejects_cuda_runtime_for_cpu_payload(runtime):
    root, model = runtime
    (root / "notices/python-environment.json").write_text(json.dumps([{"name": "torch", "version": "2.6.0+cu124"}]))
    with pytest.raises(ValueError, match="CPU payload requires"):
        payload_builder.prepare(root, model)
    assert not (root / "payload.json").exists()


def test_bad_model_download_does_not_create_payload(runtime, monkeypatch):
    root, model = runtime
    model.write_bytes(b"corrupt cache")
    monkeypatch.setattr(payload_builder.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"corrupt download"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        payload_builder.prepare(root, model)
    assert not (root / "payload.json").exists()
    assert not list((root / "models").glob("*.th"))


def test_macos_payload_and_archive_have_native_platform_and_executable_mode(runtime, tmp_path):
    import zipfile

    root, model = runtime
    (root / "stemlab-backend.exe").rename(root / "stemlab-backend")
    (root / "stemlab-backend").chmod(0o755)
    (root / "notices/python-environment.json").write_text(json.dumps([{"name": "torch", "version": "2.6.0"}]))
    payload = payload_builder.prepare(root, model, "macos-arm64")
    assert payload["platform"] == "macos-arm64"
    assert payload["executable"] == "stemlab-backend"
    output = tmp_path / "macos"
    payload_builder.archive_payload(root, output, payload)
    manifest = json.loads((output / "macos-arm64.json").read_text())
    assert "macos-runtime-" in manifest["url"]
    assert manifest["platform"] == "macos-arm64"
    with zipfile.ZipFile(next(output.glob("*.zip"))) as bundle:
        assert bundle.getinfo("stemlab-backend").file_size == len(b"cpu-exe")
