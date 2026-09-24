from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from viib_stemlab.constants import CANONICAL_STEMS


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
