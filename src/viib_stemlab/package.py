from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from viib_stemlab import __version__
from viib_stemlab.constants import (
    CANONICAL_STEMS,
    GENERATOR_NAME,
    PACKAGE_SUFFIX,
    SCHEMA_VERSION,
)
from viib_stemlab.hashing import sha256_file
from viib_stemlab.manifest import (
    AudioInfo,
    GeneratorInfo,
    ModelInfo,
    SourceInfo,
    StemFileInfo,
    StemManifest,
)
from viib_stemlab.validation import (
    PackageValidationError,
    read_wav_info,
    validate_package,
)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_source_name(source: Path) -> str:
    cleaned = _SAFE_NAME.sub("_", source.stem).strip(" ._-")
    return cleaned or "track"


def package_id(source: Path, source_sha256: str) -> str:
    return f"{safe_source_name(source)}-{source_sha256[:12]}"


def build_package_from_stems(
    *,
    source: Path,
    stems: dict[str, Path],
    output_root: Path,
    engine_name: str,
    model_name: str,
    model_version: str,
    device: str,
    overwrite: bool = False,
) -> Path:
    source = Path(source)
    output_root = Path(output_root)
    if not source.is_file():
        raise FileNotFoundError(source)

    missing = [name for name in CANONICAL_STEMS if name not in stems]
    if missing:
        raise ValueError(f"missing canonical stem outputs: {', '.join(missing)}")

    source_sha = sha256_file(source)
    pkg_id = package_id(source, source_sha)
    output_root.mkdir(parents=True, exist_ok=True)
    final_dir = output_root / f"{pkg_id}{PACKAGE_SUFFIX}"
    if final_dir.exists() and not overwrite:
        raise FileExistsError(final_dir)

    staging = output_root / f".{pkg_id}.partial-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        wav_infos = {}
        stem_entries: dict[str, StemFileInfo] = {}
        for name in CANONICAL_STEMS:
            src = Path(stems[name])
            if not src.is_file():
                raise FileNotFoundError(f"{name} stem not found: {src}")
            dest = staging / f"{name}.wav"
            shutil.copy2(src, dest)
            info = read_wav_info(dest)
            wav_infos[name] = info
            stem_entries[name] = StemFileInfo(
                file=dest.name,
                sha256=sha256_file(dest),
                sizeBytes=dest.stat().st_size,
                frames=info.frames,
            )

        first = wav_infos[CANONICAL_STEMS[0]]
        geometry_errors: list[str] = []
        for name, info in wav_infos.items():
            if info.sample_rate != first.sample_rate:
                geometry_errors.append(f"{name} sample rate does not match")
            if info.channels != first.channels:
                geometry_errors.append(f"{name} channels do not match")
            if info.frames != first.frames:
                geometry_errors.append(f"{name} frames do not match")
        if geometry_errors:
            raise PackageValidationError(geometry_errors)

        manifest = StemManifest(
            schemaVersion=SCHEMA_VERSION,
            packageId=pkg_id,
            createdAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source=SourceInfo(
                filename=source.name,
                sha256=source_sha,
                sizeBytes=source.stat().st_size,
            ),
            generator=GeneratorInfo(name=GENERATOR_NAME, version=__version__),
            model=ModelInfo(
                engine=engine_name,
                name=model_name,
                version=model_version,
                device=device,
            ),
            audio=AudioInfo(
                codec="wav",
                sampleRate=first.sample_rate,
                channels=first.channels,
                frames=first.frames,
                durationSeconds=first.duration_seconds,
            ),
            stems=stem_entries,
        )
        manifest.write(staging / "manifest.json")
        validate_package(
            staging,
            source_path=source,
            require_package_suffix=False,
        )

        backup: Path | None = None
        if final_dir.exists():
            backup = output_root / f".{pkg_id}.backup-{uuid.uuid4().hex}"
            os.replace(final_dir, backup)
        try:
            os.replace(staging, final_dir)
        except Exception:
            if backup is not None and backup.exists() and not final_dir.exists():
                os.replace(backup, final_dir)
            raise
        else:
            if backup is not None:
                shutil.rmtree(backup, ignore_errors=True)
        return final_dir
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
