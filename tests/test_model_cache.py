from __future__ import annotations

import json
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
