from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from viib_stemlab.constants import CANONICAL_STEMS
from viib_stemlab.engines.base import EngineCapabilities, SeparationResult


def write_test_wav(
    path: Path,
    *,
    frames: int = 128,
    sample_rate: int = 44100,
    channels: int = 2,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        frame = struct.pack("<h", 1000) * channels
        writer.writeframes(frame * frames)


def _caps(*devices: str) -> EngineCapabilities:
    devs = devices or ("cpu",)
    return EngineCapabilities(
        available=True,
        engine="demucs",
        version="4.0.1",
        devices=tuple(devs),
        auto_device=devs[0],
    )


class FakeEngine:
    def __init__(self, stems: dict[str, Path]):
        self.stems = stems
        self.model = "fake6"

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            available=True,
            engine="fake",
            version="1",
            devices=("cpu",),
            auto_device="cpu",
        )

    def separate(
        self,
        source: Path,
        work_dir: Path,
        *,
        device: str = "auto",
        progress=None,
        cancellation_token=None,
        fallback_to_cpu=False,
    ) -> SeparationResult:
        if progress:
            progress("separating", 1.0, "fake separation complete")
        return SeparationResult(
            stems=self.stems,
            engine="fake",
            model="fake6",
            version="1",
            device="cpu",
        )


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    source = tmp_path / "source.flac"
    source.write_bytes(b"synthetic-source-for-package-identity")
    return source


@pytest.fixture
def stem_files(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "engine-output"
    result = {}
    for name in CANONICAL_STEMS:
        path = root / f"{name}.wav"
        write_test_wav(path, frames=256, sample_rate=44100, channels=2)
        result[name] = path
    return result
