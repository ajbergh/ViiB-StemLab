from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from viib_stemlab import __version__
from viib_stemlab.constants import (
    CANONICAL_STEMS,
    GENERATOR_NAME,
    PACKAGE_SUFFIX,
    SCHEMA_VERSION,
    STEM_LAYOUT,
)
from viib_stemlab.errors import (
    OutputGeometryMismatchError,
    OutputMissingError,
    PackageExistsError,
    SourceNotFoundError,
)
from viib_stemlab.hashing import sha256_file
from viib_stemlab.manifest import (
    AudioInfo,
    GeneratorInfo,
    ModelInfo,
    SourceInfo,
    StemFileInfo,
    StemManifest,
    TimingInfo,
)
from viib_stemlab.progress import ProgressCallback, ProgressEmitter
from viib_stemlab.validation import read_stem_wav_format, validate_package

if TYPE_CHECKING:
    from viib_stemlab.cancellation import CancellationToken

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
    cancellation_token: CancellationToken | None = None,
    progress: ProgressCallback | None = None,
) -> Path:
    if cancellation_token:
        cancellation_token.raise_if_cancelled()

    source = Path(source)
    output_root = Path(output_root)
    if not source.is_file():
        raise SourceNotFoundError(f"Source file not found: {source}")

    missing = [name for name in CANONICAL_STEMS if name not in stems]
    if missing:
        raise OutputMissingError(f"missing canonical stem outputs: {', '.join(missing)}")

    emitter = ProgressEmitter(progress)
    source_sha = sha256_file(source)
    pkg_id = package_id(source, source_sha)
    output_root.mkdir(parents=True, exist_ok=True)
    final_dir = output_root / f"{pkg_id}{PACKAGE_SUFFIX}"
    if final_dir.exists() and not overwrite:
        raise PackageExistsError(f"Package directory already exists: {final_dir}")

    staging = output_root / f".{pkg_id}.partial-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        wav_infos = {}
        stem_entries: dict[str, StemFileInfo] = {}
        for name in CANONICAL_STEMS:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()

            src = Path(stems[name])
            if not src.is_file():
                raise OutputMissingError(f"{name} stem not found: {src}")
            dest = staging / f"{name}.wav"
            shutil.copy2(src, dest)
            try:
                info = read_stem_wav_format(dest)
            except ValueError as exc:
                raise OutputGeometryMismatchError(
                    f"{name} stem is not a v1 WAV (PCM16 or float32): {exc}",
                    details={"stem": name},
                ) from exc
            wav_infos[name] = info
            stem_entries[name] = StemFileInfo(
                path=dest.name,
                sha256=sha256_file(dest),
                sizeBytes=dest.stat().st_size,
                sampleRate=info.sample_rate,
                channels=info.channels,
                frames=info.frames,
                encoding=info.encoding,
            )

        if cancellation_token:
            cancellation_token.raise_if_cancelled()

        first = wav_infos[CANONICAL_STEMS[0]]
        geometry_errors: list[str] = []
        for name, info in wav_infos.items():
            if info.sample_rate != first.sample_rate:
                geometry_errors.append(f"{name} sample rate does not match")
            if info.channels != first.channels:
                geometry_errors.append(f"{name} channels do not match")
            if info.frames != first.frames:
                geometry_errors.append(f"{name} frames do not match")
            if info.encoding != first.encoding:
                geometry_errors.append(f"{name} encoding does not match")
        if geometry_errors:
            raise OutputGeometryMismatchError(
                "; ".join(geometry_errors),
                details={"geometry_errors": geometry_errors},
            )

        manifest = StemManifest(
            schemaVersion=SCHEMA_VERSION,
            packageId=pkg_id,
            createdAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source=SourceInfo(
                filename=source.name,
                sha256=source_sha,
                duration=first.frames / first.sample_rate,
                sizeBytes=source.stat().st_size,
            ),
            stemLayout=STEM_LAYOUT,
            generator=GeneratorInfo(name=GENERATOR_NAME, version=__version__),
            model=ModelInfo(
                name=model_name,
                version=model_version,
                engine=engine_name,
                device=device,
            ),
            audio=AudioInfo(
                sampleRate=first.sample_rate,
                channels=first.channels,
                frames=first.frames,
            ),
            # StemLab packages the separator output as-is: no decoder-delay
            # compensation or start trim is applied.
            timing=TimingInfo(),
            stems=stem_entries,
        )
        manifest.write(staging / "manifest.json")

        emitter.emit("validating", 0.0, "Validating staging package")
        validate_package(
            staging,
            source_path=source,
            require_package_suffix=False,
        )

        if cancellation_token:
            cancellation_token.raise_if_cancelled()

        emitter.emit("finalizing", 0.0, f"Promoting package {final_dir.name}")
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
