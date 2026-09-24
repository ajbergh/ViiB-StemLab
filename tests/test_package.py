from __future__ import annotations

import json
from pathlib import Path

import pytest

import viib_stemlab.package as package_module
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


def test_overwrite_promotion_failure_restores_previous_package(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
    monkeypatch,
) -> None:
    library = tmp_path / "library"
    package = build_package_from_stems(
        source=source_file,
        stems=stem_files,
        output_root=library,
        engine_name="fake",
        model_name="original",
        model_version="1.0",
        device="cpu",
    )
    original_manifest = (package / "manifest.json").read_bytes()

    real_replace = package_module.os.replace
    failed = False

    def fail_final_promotion(src, dst):
        nonlocal failed
        source = Path(src)
        destination = Path(dst)
        if (
            not failed
            and source.name.startswith(".")
            and ".partial-" in source.name
            and destination == package
        ):
            failed = True
            raise OSError("synthetic promotion failure")
        return real_replace(src, dst)

    monkeypatch.setattr(package_module.os, "replace", fail_final_promotion)

    with pytest.raises(OSError, match="synthetic promotion failure"):
        build_package_from_stems(
            source=source_file,
            stems=stem_files,
            output_root=library,
            engine_name="fake",
            model_name="replacement",
            model_version="2.0",
            device="cpu",
            overwrite=True,
        )

    assert package.is_dir()
    assert (package / "manifest.json").read_bytes() == original_manifest
    assert not list(library.glob(".*.partial-*"))
    assert not list(library.glob(".*.backup-*"))
