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
    (root / "notices/python-environment.json").write_text(json.dumps([{"name": "torch", "version": "2.6.0+cpu"}, {"name": "demucs", "version": "4.1.0"}]))
    model = tmp_path / "weights"
    model.mkdir()
    for checkpoint in payload_builder.FT_CHECKPOINTS:
        content = checkpoint["filename"].encode()
        (model / checkpoint["filename"]).write_bytes(content)
        monkeypatch.setitem(checkpoint, "expected_size_bytes", len(content))
        monkeypatch.setitem(checkpoint, "sha256", hashlib.sha256(content).hexdigest())
    return root, model


def test_full_payload_inventories_model_and_archive(runtime, tmp_path):
    root, model = runtime
    payload = payload_builder.prepare(root, model)
    assert len(payload["models"]) == 5
    assert all(name in payload["files"] for name in payload["models"])
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
    for checkpoint in model.iterdir():
        checkpoint.write_bytes(b"corrupt cache")
    monkeypatch.setattr(payload_builder.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"corrupt download"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        payload_builder.prepare(root, model)
    assert not (root / "payload.json").exists()
    assert not list((root / "models").rglob("*.safetensors"))


def test_macos_payload_and_archive_have_native_platform_and_executable_mode(runtime, tmp_path):
    import zipfile

    root, model = runtime
    (root / "stemlab-backend.exe").rename(root / "stemlab-backend")
    (root / "stemlab-backend").chmod(0o755)
    (root / "notices/python-environment.json").write_text(json.dumps([{"name": "torch", "version": "2.6.0"}, {"name": "demucs", "version": "4.1.0"}]))
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


def test_rejects_old_demucs_runtime_before_bundling_models(runtime):
    root, model = runtime
    (root / "notices/python-environment.json").write_text(json.dumps([
        {"name": "torch", "version": "2.6.0+cpu"}, {"name": "demucs", "version": "4.0.1"},
    ]))
    with pytest.raises(ValueError, match="requires Demucs 4.1.0"):
        payload_builder.prepare(root, model)
    assert not (root / "payload.json").exists()


def test_linux_payload_uses_cpu_identity_and_linux_download_endpoint(runtime, tmp_path):
    import os
    import zipfile

    root, model = runtime
    executable = root / "stemlab-backend"
    (root / "stemlab-backend.exe").rename(executable)
    executable.chmod(0o755)
    payload = payload_builder.prepare(root, model, "linux-x64")
    assert payload["platform"] == "linux-x64"
    assert payload["executable"] == "stemlab-backend"
    assert "-cpu-demucs410-" in payload["version"]
    output = tmp_path / "linux"
    payload_builder.archive_payload(root, output, payload)
    release = json.loads((output / "linux-x64.json").read_text())
    archive = next(output.glob("*.zip"))
    assert release["url"].endswith(f"/linux-runtime-{payload['appVersion']}/{archive.name}")
    assert release["platform"] == "linux-x64"
    assert release["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.read("stemlab-backend") == b"cpu-exe"
        if os.name == "posix":
            assert (bundle.getinfo("stemlab-backend").external_attr >> 16) & 0o111


def test_linux_rejects_non_cpu_torch(runtime):
    root, model = runtime
    (root / "stemlab-backend.exe").rename(root / "stemlab-backend")
    (root / "notices/python-environment.json").write_text(json.dumps([
        {"name": "torch", "version": "2.6.0"}, {"name": "demucs", "version": "4.1.0"},
    ]))
    with pytest.raises(ValueError, match="CPU payload requires"):
        payload_builder.prepare(root, model, "linux-x64")
