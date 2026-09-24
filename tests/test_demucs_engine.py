from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from conftest import write_test_wav

from viib_stemlab.constants import CANONICAL_STEMS
from viib_stemlab.engines.base import EngineCapabilities
from viib_stemlab.engines.demucs import DemucsEngine, DemucsUnavailableError


def _caps(*devices: str, auto: str = "cpu") -> EngineCapabilities:
    return EngineCapabilities(
        available=True,
        engine="demucs",
        version="4.0.1",
        devices=devices,
        auto_device=auto,
    )


def test_resolve_device_uses_auto_capability(monkeypatch) -> None:
    engine = DemucsEngine()
    monkeypatch.setattr(engine, "capabilities", lambda: _caps("cpu", "cuda", auto="cuda"))

    assert engine.resolve_device("auto") == "cuda"
    assert engine.resolve_device("cpu") == "cpu"


def test_resolve_device_rejects_unavailable_device(monkeypatch) -> None:
    engine = DemucsEngine()
    monkeypatch.setattr(engine, "capabilities", lambda: _caps("cpu"))

    with pytest.raises(DemucsUnavailableError):
        engine.resolve_device("cuda")


def test_separate_builds_demucs_command_and_collects_stems(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "track.wav"
    write_test_wav(source, frames=32)
    work_dir = tmp_path / "work"
    engine = DemucsEngine(model="htdemucs_6s")

    monkeypatch.setattr(
        engine,
        "capabilities",
        lambda: _caps("cpu", "cuda", auto="cuda"),
    )
    monkeypatch.setattr(engine, "resolve_device", lambda requested: "cuda")

    captured: dict[str, object] = {}

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(["10% separating\n", "100% done\n"])

        def wait(self) -> int:
            return 0

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output = work_dir / "htdemucs_6s" / source.stem
        for name in CANONICAL_STEMS:
            write_test_wav(output / f"{name}.wav", frames=32)
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    events: list[tuple[str, float | None, str | None]] = []

    result = engine.separate(
        source,
        work_dir,
        device="auto",
        progress=lambda stage, value, message: events.append((stage, value, message)),
    )

    command = captured["command"]
    assert command == [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n",
        "htdemucs_6s",
        "-d",
        "cuda",
        "-o",
        str(work_dir),
        str(source),
    ]
    assert result.device == "cuda"
    assert result.version == "4.0.1"
    assert set(result.stems) == set(CANONICAL_STEMS)
    assert any(value == 0.1 for _, value, _ in events)
    assert events[-1][1] == 1.0


def test_separate_surfaces_process_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "track.wav"
    write_test_wav(source, frames=32)
    engine = DemucsEngine()

    monkeypatch.setattr(engine, "capabilities", lambda: _caps("cpu"))
    monkeypatch.setattr(engine, "resolve_device", lambda requested: "cpu")

    class FakeProcess:
        stdout = iter(["model failed badly\n"])

        def wait(self) -> int:
            return 7

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    with pytest.raises(RuntimeError, match="model failed badly"):
        engine.separate(source, tmp_path / "work", device="cpu")


def test_separate_terminates_child_on_keyboard_interrupt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "track.wav"
    write_test_wav(source, frames=32)
    engine = DemucsEngine()

    monkeypatch.setattr(engine, "capabilities", lambda: _caps("cpu"))
    monkeypatch.setattr(engine, "resolve_device", lambda requested: "cpu")

    class InterruptingOutput:
        def __iter__(self):
            return self

        def __next__(self):
            raise KeyboardInterrupt

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = InterruptingOutput()
            self.terminated = False
            self.killed = False

        def poll(self):
            return 130 if self.terminated or self.killed else None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout=None) -> int:
            return 130

    process = FakeProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

    with pytest.raises(KeyboardInterrupt):
        engine.separate(source, tmp_path / "work", device="cpu")

    assert process.terminated is True
    assert process.killed is False



@pytest.mark.parametrize("suffix", [".mp3", ".ogg"])
def test_separate_passes_compressed_source_to_demucs(
    tmp_path: Path,
    monkeypatch,
    suffix: str,
) -> None:
    source = tmp_path / f"track{suffix}"
    source.write_bytes(b"compressed-audio-fixture")
    work_dir = tmp_path / "work"
    engine = DemucsEngine(model="htdemucs_6s")

    monkeypatch.setattr(engine, "capabilities", lambda: _caps("cpu"))
    monkeypatch.setattr(engine, "resolve_device", lambda requested: "cpu")
    captured: dict[str, object] = {}

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(["100% done\n"])

        def wait(self) -> int:
            return 0

    def fake_popen(command, **kwargs):
        captured["command"] = command
        output = work_dir / "htdemucs_6s" / source.stem
        for name in CANONICAL_STEMS:
            write_test_wav(output / f"{name}.wav", frames=32)
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = engine.separate(source, work_dir, device="cpu")

    assert captured["command"][-1] == str(source)
    assert set(result.stems) == set(CANONICAL_STEMS)
