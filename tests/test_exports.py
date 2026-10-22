from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import FakeEngine

import viib_stemlab.exports as exports
import viib_stemlab.package as package_module
from viib_stemlab.cancellation import CancellationToken
from viib_stemlab.cli import build_parser
from viib_stemlab.errors import GenerationCancelledError, StemLabError
from viib_stemlab.package import build_package_from_stems
from viib_stemlab.queue.runner import QueueRunner
from viib_stemlab.queue.store import QueueStore
from viib_stemlab.ui.settings import SettingsStore
from viib_stemlab.validation import validate_package


def build(source_file, stem_files, tmp_path, **kwargs):
    return build_package_from_stems(
        source=source_file, stems=stem_files, output_root=tmp_path / "library",
        engine_name="fake", model_name="fake6", model_version="1", device="cpu", **kwargs,
    )


@pytest.mark.parametrize("output_format,codec", [("mp3", "mp3"), ("ogg", "vorbis")])
def test_compressed_queue_export(tmp_path, source_file, stem_files, output_format, codec):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe required for codec smoke test")
    store = QueueStore(tmp_path / "queue.db")
    job = store.add_job(source_file, tmp_path / "library", output_format=output_format)
    # Reopen the store to verify durability as well as runner propagation.
    store = QueueStore(tmp_path / "queue.db")
    assert store.get_job(job.id).output_format == output_format
    assert QueueRunner(store, engine=FakeEngine(stem_files)).run_next()
    completed = store.get_job(job.id)
    assert completed.status == "complete", completed.diagnostic_message
    package = Path(completed.package_path)
    manifest = validate_package(package)
    assert manifest.requiredFeatures == ("compressed-stems-v1",)
    assert all(stem.path.endswith(f".{output_format}") for stem in manifest.stems.values())
    assert len(list(package.glob(f"*.{output_format}"))) == 6
    assert not list(package.rglob("*.wav"))
    assert not (package / "exports").exists()
    for name in stem_files:
        audio = package / f"{name}.{output_format}"
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(audio)],
            capture_output=True, text=True, check=True,
        )
        stream = json.loads(result.stdout)["streams"][0]
        assert stream["codec_name"] == codec
        assert int(stream["sample_rate"]) == 44100
        assert stream["channels"] == 2
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(audio), "-f", "s16le", "-"],
            capture_output=True, check=True,
        )
        assert len(decoded.stdout) > 0


@pytest.mark.parametrize("output_format", ["ogg", "mp3"])
def test_soundfile_fallback(tmp_path, stem_files, monkeypatch, output_format):
    pytest.importorskip("soundfile")
    if exports._soundfile_encoder(output_format) is None:
        pytest.skip("Installed libsndfile lacks this codec")
    monkeypatch.setattr(exports.shutil, "which", lambda _: None)
    encode = exports.prepare_export(output_format)
    output = tmp_path / f"vocals.{output_format}"
    encode(stem_files["vocals"], output, None)
    import soundfile as sf

    audio, rate = sf.read(output, always_2d=True)
    assert rate == 44100
    assert audio.shape[1] == 2
    assert len(audio) > 0


@pytest.mark.parametrize("cancel", [False, True])
def test_export_failure_preserves_previous_package(tmp_path, source_file, stem_files, monkeypatch, cancel):
    package = build(source_file, stem_files, tmp_path)
    original = (package / "manifest.json").read_bytes()
    token = CancellationToken()

    def fail(source, destination, cancellation_token):
        destination.write_bytes(b"partial export")
        if cancel:
            cancellation_token.cancel()
            cancellation_token.raise_if_cancelled()
        raise StemLabError("encoder failed")

    monkeypatch.setattr(package_module, "prepare_export", lambda _: fail)
    with pytest.raises(GenerationCancelledError if cancel else StemLabError):
        build(source_file, stem_files, tmp_path, output_format="mp3", overwrite=True,
              cancellation_token=token)
    assert (package / "manifest.json").read_bytes() == original
    validate_package(package)
    assert not (package / "exports").exists()
    assert not list(package.parent.glob("*.partial-*"))


def test_missing_encoder_is_actionable(monkeypatch):
    monkeypatch.setattr(exports.shutil, "which", lambda _: None)
    monkeypatch.setattr(exports, "_soundfile_encoder", lambda _: None)
    with pytest.raises(StemLabError, match="requires FFmpeg") as error:
        exports.prepare_export("mp3")
    assert "libmp3lame" in error.value.diagnostic
    assert exports.prepare_export("wav") is None
    with pytest.raises(ValueError):
        exports.prepare_export("aac")


def test_ffmpeg_cancellation_reaps_process(tmp_path, stem_files, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required")
    encode = exports.prepare_export("mp3")
    token = CancellationToken()
    original_popen = subprocess.Popen
    processes = []

    def popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        token.cancel()
        return process

    monkeypatch.setattr(exports.subprocess, "Popen", popen)
    with pytest.raises(GenerationCancelledError):
        encode(stem_files["vocals"], tmp_path / "cancelled.mp3", token)
    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_queue_migration_and_settings(tmp_path, source_file):
    db = tmp_path / "queue.db"
    store = QueueStore(db)
    job = store.add_job(source_file, tmp_path / "library")
    with store._get_connection() as conn:
        conn.execute("ALTER TABLE jobs DROP COLUMN output_format")
    store = QueueStore(db)
    assert store.get_job(job.id).output_format == "wav"
    settings = SettingsStore(tmp_path / "settings.json", str(tmp_path / "library"))
    assert settings.get()["output_format"] == "wav"
    settings.update({"output_format": "ogg"})
    assert SettingsStore(settings.path, "unused").get()["output_format"] == "ogg"
    with pytest.raises(ValueError):
        settings.update({"output_format": "aac"})


@pytest.mark.parametrize("command", [
    ["generate", "song.wav", "--output", "library"],
    ["package", "build", "--source", "song.wav", "--stems-dir", "stems", "--output", "library"],
    ["queue", "add", "song.wav", "--output", "library"],
])
def test_cli_formats(command):
    parser = build_parser()
    assert parser.parse_args(command).output_format == "wav"
    for output_format in ("ogg", "mp3"):
        assert parser.parse_args([*command, "--output-format", output_format]).output_format == output_format
