from __future__ import annotations

import json
from pathlib import Path

import pytest

from viib_stemlab.hashing import sha256_file
from viib_stemlab.package import build_package_from_stems
from viib_stemlab.validation import PackageValidationError, validate_package


def test_build_and_validate_package(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    package = build_package_from_stems(
        source=source_file,
        stems=stem_files,
        output_root=tmp_path / "library",
        engine_name="fake",
        model_name="fake6",
        model_version="1.0",
        device="cpu",
    )

    manifest = validate_package(package, source_path=source_file)
    assert package.name.endswith(".viibstems")
    assert manifest.source.sha256 == sha256_file(source_file)
    assert manifest.audio.sampleRate == 44100
    assert manifest.audio.channels == 2
    assert manifest.audio.frames == 256
    assert set(manifest.stems) == {"vocals", "drums", "bass", "guitar", "piano", "other"}


def test_checksum_tamper_is_rejected(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    package = build_package_from_stems(
        source=source_file,
        stems=stem_files,
        output_root=tmp_path / "library",
        engine_name="fake",
        model_name="fake6",
        model_version="1.0",
        device="cpu",
    )
    with (package / "vocals.wav").open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(PackageValidationError) as exc:
        validate_package(package)

    assert any("vocals: size mismatch" in error for error in exc.value.errors)
    assert any("vocals: SHA-256 mismatch" in error for error in exc.value.errors)


def test_path_traversal_is_rejected(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    package = build_package_from_stems(
        source=source_file,
        stems=stem_files,
        output_root=tmp_path / "library",
        engine_name="fake",
        model_name="fake6",
        model_version="1.0",
        device="cpu",
    )
    manifest_path = package / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["stems"]["vocals"]["file"] = "../escape.wav"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PackageValidationError) as exc:
        validate_package(package, verify_hashes=False)

    assert any("unsafe package-relative path" in error for error in exc.value.errors)


def test_geometry_mismatch_is_rejected_before_finalization(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    from conftest import write_test_wav

    write_test_wav(stem_files["piano"], frames=255)

    with pytest.raises(PackageValidationError):
        build_package_from_stems(
            source=source_file,
            stems=stem_files,
            output_root=tmp_path / "library",
            engine_name="fake",
            model_name="fake6",
            model_version="1.0",
            device="cpu",
        )

    assert not list((tmp_path / "library").glob("*.viibstems"))
