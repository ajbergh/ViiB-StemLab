from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

from viib_stemlab.cli import main
from viib_stemlab.errors import ModelDownloadError, ModelMissingError
from viib_stemlab.models import KNOWN_MODELS, ModelCacheManager


def test_cache_dir_resolution(tmp_path: Path, monkeypatch) -> None:
    # 1. Explicit
    explicit = tmp_path / "custom-cache"
    mgr = ModelCacheManager(cache_dir=explicit)
    assert mgr.cache_dir == explicit

    # 2. VIIB_STEMLAB_CACHE_DIR
    env_cache = tmp_path / "env-cache"
    monkeypatch.setenv("VIIB_STEMLAB_CACHE_DIR", str(env_cache))
    mgr2 = ModelCacheManager()
    assert mgr2.cache_dir == env_cache

    # 3. TORCH_HOME
    monkeypatch.delenv("VIIB_STEMLAB_CACHE_DIR", raising=False)
    torch_home = tmp_path / "torch-home"
    monkeypatch.setenv("TORCH_HOME", str(torch_home))
    mgr3 = ModelCacheManager()
    assert mgr3.cache_dir == torch_home / "hub" / "checkpoints"


def test_model_cache_info_and_status(tmp_path: Path) -> None:
    mgr = ModelCacheManager(cache_dir=tmp_path)
    model_name = "htdemucs_6s"
    expected_file = KNOWN_MODELS[model_name]["filename"]

    # Initially uncached
    assert not mgr.is_model_cached(model_name)
    info = mgr.get_model_info(model_name)
    assert not info.cached
    assert info.local_path is None

    # Simulate presence of weights file
    weight_file = tmp_path / expected_file
    weight_file.write_bytes(b"dummy-model-weights-content")

    assert mgr.is_model_cached(model_name)
    info2 = mgr.get_model_info(model_name)
    assert info2.cached
    assert info2.local_path == weight_file
    assert info2.size_bytes == len(b"dummy-model-weights-content")


def test_preflight_model_missing_when_download_disallowed(tmp_path: Path) -> None:
    mgr = ModelCacheManager(cache_dir=tmp_path)
    with pytest.raises(ModelMissingError) as exc_info:
        mgr.preflight_model("htdemucs_6s", allow_download=False)

    assert exc_info.value.code == "model_missing"
    assert "not present in cache" in exc_info.value.message


def test_model_download_handles_network_failure(monkeypatch, tmp_path: Path) -> None:
    mgr = ModelCacheManager(cache_dir=tmp_path)

    import urllib.error

    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ModelDownloadError) as exc_info:
        mgr.download_model("htdemucs_6s")

    assert exc_info.value.code == "model_download_failed"
    assert "Failed to download model weights" in exc_info.value.message


def test_model_download_rejects_corrupt_content_before_cache_promotion(monkeypatch, tmp_path):
    class Response(BytesIO):
        headers = {"Content-Length": "7"}

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response(b"corrupt"))
    with pytest.raises(ModelDownloadError, match="checksum mismatch"):
        ModelCacheManager(tmp_path).download_model("htdemucs_6s")
    assert list(tmp_path.iterdir()) == []


def test_cli_doctor_reports_model_cache(capsys) -> None:
    assert main(["doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert "modelCache" in report
    assert "directory" in report["modelCache"]
    assert "models" in report["modelCache"]
    assert len(report["modelCache"]["models"]) >= 1


def test_cli_model_status_command(capsys, tmp_path: Path) -> None:
    assert main(["model", "status", "--cache-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Model cache directory:" in out
    assert "htdemucs_6s" in out


def test_ft_download_resumes_partial_bundle_and_reports_total_progress(tmp_path, monkeypatch):
    import hashlib
    import urllib.error

    from viib_stemlab.models import FT_CHECKPOINTS

    contents = {}
    for item in FT_CHECKPOINTS:
        data = item["filename"].encode()
        contents[item["url"]] = data
        monkeypatch.setitem(item, "sha256", hashlib.sha256(data).hexdigest())
        monkeypatch.setitem(item, "sha256_prefix", hashlib.sha256(data).hexdigest()[:8])
        monkeypatch.setitem(item, "expected_size_bytes", len(data))

    calls = []
    fail = True

    def download(request, **kwargs):
        calls.append(request.full_url)
        if fail and request.full_url == FT_CHECKPOINTS[1]["url"]:
            raise urllib.error.URLError("interrupted")
        data = contents[request.full_url]
        response = BytesIO(data)
        response.headers = {"Content-Length": str(len(data))}
        return response

    monkeypatch.setattr("urllib.request.urlopen", download)
    manager = ModelCacheManager(tmp_path)
    with pytest.raises(ModelDownloadError):
        manager.download_model("htdemucs_ft")
    assert not manager.is_model_cached("htdemucs_ft")
    with pytest.raises(ModelMissingError):
        manager.preflight_model("htdemucs_ft", allow_download=False)
    assert len(list(tmp_path.rglob("*.yaml"))) == 1
    assert not list(tmp_path.glob("*.partial"))

    fail = False
    progress = []
    info = manager.preflight_model("htdemucs_ft", progress=progress.append)
    assert info.cached
    assert info.size_bytes == sum(map(len, contents.values()))
    assert info.expected_size_bytes == info.size_bytes
    assert len(list(tmp_path.rglob("*.safetensors"))) == 4
    assert calls.count(FT_CHECKPOINTS[0]["url"]) == 1
    values = [event.progress for event in progress if event.progress is not None]
    assert values == sorted(values)
    assert values[-1] == 1.0


def test_safetensors_cache_rejects_corruption_and_wrong_revision(tmp_path, monkeypatch):
    import hashlib

    from viib_stemlab.models import FT_CHECKPOINTS, FT_HUB_REPO

    manager = ModelCacheManager(tmp_path)
    for item in FT_CHECKPOINTS:
        content = item["filename"].encode()
        monkeypatch.setitem(item, "expected_size_bytes", len(content))
        monkeypatch.setitem(item, "sha256", hashlib.sha256(content).hexdigest())
        target = tmp_path / item["cache_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manager.write_hf_reference()
    assert manager.is_model_cached("htdemucs_ft")
    target = tmp_path / FT_CHECKPOINTS[1]["cache_path"]
    target.write_bytes(b"x" * target.stat().st_size)
    assert not manager.is_model_cached("htdemucs_ft")
    with pytest.raises(ModelMissingError):
        manager.preflight_model("htdemucs_ft", allow_download=False)
    target.write_bytes(FT_CHECKPOINTS[1]["filename"].encode())
    reference = manager.get_hf_cache() / FT_HUB_REPO / "refs/main"
    reference.write_text("wrong-revision")
    assert not manager.is_model_cached("htdemucs_ft")
