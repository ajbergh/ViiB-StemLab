from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import pytest

from viib_stemlab.cli import main
from viib_stemlab.upgrade import LEGACY_BACKUP_NAME, upgrade_package, upgrade_packages
from viib_stemlab.validation import read_stem_wav_format, validate_package

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LEGACY = FIXTURES / "package-v0-legacy.viibstems"


@pytest.fixture
def legacy_package(tmp_path: Path) -> Path:
    target = tmp_path / "library" / LEGACY.name
    shutil.copytree(LEGACY, target)
    return target


def _write_wav(path: Path, *, format_tag: int, bits: int, frames: int = 8, channels: int = 2) -> None:
    block = channels * bits // 8
    data = b"\x00" * (block * frames)
    fmt = struct.pack("<HHIIHH", format_tag, channels, 44100, 44100 * block, block, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def test_legacy_fixture_is_rejected_until_upgraded(legacy_package: Path) -> None:
    with pytest.raises(Exception) as exc:
        validate_package(legacy_package)
    assert "viib-stemlab package upgrade" in str(exc.value)


def test_upgrade_rewrites_manifest_and_keeps_audio(legacy_package: Path) -> None:
    original = (legacy_package / "manifest.json").read_bytes()
    audio_before = {p.name: p.read_bytes() for p in legacy_package.glob("*.wav")}

    outcome = upgrade_package(legacy_package)

    assert outcome.status == "upgraded", outcome.detail
    assert (legacy_package / LEGACY_BACKUP_NAME).read_bytes() == original
    assert {p.name: p.read_bytes() for p in legacy_package.glob("*.wav")} == audio_before
    manifest = validate_package(legacy_package)
    assert manifest.stemLayout == "six"
    assert all(stem.encoding == "pcm_s16le" for stem in manifest.stems.values())
    data = json.loads((legacy_package / "manifest.json").read_text(encoding="utf-8"))
    assert data["timing"] == {"decoderDelayFrames": 0, "startTrimFrames": 0}
    assert "file" not in data["stems"]["vocals"]


def test_upgrade_is_idempotent(legacy_package: Path) -> None:
    assert upgrade_package(legacy_package).status == "upgraded"
    upgraded = (legacy_package / "manifest.json").read_bytes()
    backup = (legacy_package / LEGACY_BACKUP_NAME).read_bytes()
    assert upgrade_package(legacy_package).status == "already-v1"
    assert (legacy_package / "manifest.json").read_bytes() == upgraded
    assert (legacy_package / LEGACY_BACKUP_NAME).read_bytes() == backup


def test_dry_run_writes_nothing(legacy_package: Path) -> None:
    original = (legacy_package / "manifest.json").read_bytes()
    assert upgrade_package(legacy_package, dry_run=True).status == "would-upgrade"
    assert (legacy_package / "manifest.json").read_bytes() == original
    assert not (legacy_package / LEGACY_BACKUP_NAME).exists()


def test_failed_validation_restores_original_manifest(legacy_package: Path) -> None:
    original = (legacy_package / "manifest.json").read_bytes()
    vocals = legacy_package / "vocals.wav"
    data = bytearray(vocals.read_bytes())
    data[-1] ^= 0xFF  # same size and header, different bytes -> checksum mismatch
    vocals.write_bytes(bytes(data))

    outcome = upgrade_package(legacy_package)

    assert outcome.status == "failed"
    assert "vocals: SHA-256 mismatch" in outcome.detail
    assert (legacy_package / "manifest.json").read_bytes() == original


def test_upgrade_packages_walks_a_library(tmp_path: Path) -> None:
    library = tmp_path / "library"
    for index in range(3):
        shutil.copytree(LEGACY, library / "nested" / f"track-{index}.viibstems")
    shutil.copytree(FIXTURES / "package-v1-valid.viibstems", library / "already.viibstems")

    report = upgrade_packages(library)

    assert report.count("upgraded") == 3
    assert report.count("already-v1") == 1
    assert report.count("failed") == 0


def test_cli_package_upgrade(legacy_package: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["package", "upgrade", str(legacy_package.parent), "--dry-run"]) == 0
    assert "1 would upgrade" in capsys.readouterr().out
    assert main(["package", "upgrade", str(legacy_package.parent)]) == 0
    assert "1 upgraded" in capsys.readouterr().out
    assert main(["package", "validate", str(legacy_package)]) == 0


def test_stem_wav_parser_classifies_v1_encodings(tmp_path: Path) -> None:
    pcm16 = tmp_path / "pcm16.wav"
    float32 = tmp_path / "float32.wav"
    extensible = tmp_path / "extensible-float.wav"
    _write_wav(pcm16, format_tag=1, bits=16)
    _write_wav(float32, format_tag=3, bits=32)
    # WAVE_FORMAT_EXTENSIBLE with an IEEE float SubFormat.
    block = 8
    fmt = struct.pack("<HHIIHH", 0xFFFE, 2, 44100, 44100 * block, block, 32)
    fmt += struct.pack("<HHI", 22, 32, 3) + struct.pack("<H", 3) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
    data = b"\x00" * block * 4
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    extensible.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)

    assert read_stem_wav_format(pcm16).encoding == "pcm_s16le"
    assert read_stem_wav_format(float32).encoding == "float32le"
    parsed = read_stem_wav_format(extensible)
    assert (parsed.encoding, parsed.frames) == ("float32le", 4)


def test_stem_wav_parser_rejects_other_encodings(tmp_path: Path) -> None:
    pcm24 = tmp_path / "pcm24.wav"
    _write_wav(pcm24, format_tag=1, bits=24)
    with pytest.raises(ValueError, match="PCM16 or float32"):
        read_stem_wav_format(pcm24)
