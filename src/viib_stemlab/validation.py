from __future__ import annotations

import re
import wave
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from viib_stemlab.constants import CANONICAL_STEMS, PACKAGE_SUFFIX, SUPPORTED_PACKAGE_CODECS
from viib_stemlab.errors import PackageValidationError
from viib_stemlab.hashing import sha256_file
from viib_stemlab.manifest import StemManifest

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class WavInfo:
    sample_rate: int
    channels: int
    frames: int

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate


def read_wav_info(path: Path) -> WavInfo:
    try:
        with wave.open(str(path), "rb") as reader:
            return WavInfo(
                sample_rate=reader.getframerate(),
                channels=reader.getnchannels(),
                frames=reader.getnframes(),
            )
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"invalid WAV file {path.name}: {exc}") from exc


def safe_member_path(package_dir: Path, raw: str) -> Path:
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or normalized.startswith("//")
        or _WINDOWS_DRIVE.match(normalized)
        or posix.is_absolute()
        or ".." in posix.parts
    ):
        raise ValueError(f"unsafe package-relative path: {raw!r}")

    candidate = package_dir.joinpath(*posix.parts)
    root = package_dir.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"path escapes package directory: {raw!r}")
    return candidate


def validate_package(
    package_dir: Path,
    *,
    source_path: Path | None = None,
    verify_hashes: bool = True,
    require_package_suffix: bool = True,
) -> StemManifest:
    package_dir = Path(package_dir)
    errors: list[str] = []

    if not package_dir.is_dir():
        raise PackageValidationError([f"package directory not found: {package_dir}"])
    if require_package_suffix and not package_dir.name.endswith(PACKAGE_SUFFIX):
        errors.append(f"package directory must end with {PACKAGE_SUFFIX}")

    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        raise PackageValidationError(errors + ["manifest.json is missing"])

    try:
        manifest = StemManifest.load(manifest_path)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise PackageValidationError(errors + [f"manifest is invalid: {exc}"]) from exc

    errors.extend(manifest.structural_errors())

    if manifest.audio.codec not in SUPPORTED_PACKAGE_CODECS:
        errors.append(
            f"unsupported package codec {manifest.audio.codec!r}; "
            f"supported: {', '.join(SUPPORTED_PACKAGE_CODECS)}"
        )

    if source_path is not None:
        source_path = Path(source_path)
        if not source_path.is_file():
            errors.append(f"source file not found: {source_path}")
        else:
            if source_path.stat().st_size != manifest.source.sizeBytes:
                errors.append("source size does not match manifest")
            if verify_hashes and sha256_file(source_path) != manifest.source.sha256:
                errors.append("source SHA-256 does not match manifest")

    seen: set[Path] = set()
    for name in CANONICAL_STEMS:
        stem = manifest.stems.get(name)
        if stem is None:
            continue
        try:
            stem_path = safe_member_path(package_dir, stem.file)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue

        resolved = stem_path.resolve()
        if resolved in seen:
            errors.append(f"{name}: duplicate stem file path {stem.file!r}")
            continue
        seen.add(resolved)

        if not stem_path.is_file():
            errors.append(f"{name}: stem file missing: {stem.file}")
            continue
        if stem_path.stat().st_size != stem.sizeBytes:
            errors.append(
                f"{name}: size mismatch (manifest={stem.sizeBytes}, actual={stem_path.stat().st_size})"
            )
        if verify_hashes and sha256_file(stem_path) != stem.sha256:
            errors.append(f"{name}: SHA-256 mismatch")

        if manifest.audio.codec == "wav":
            try:
                info = read_wav_info(stem_path)
            except ValueError as exc:
                errors.append(f"{name}: {exc}")
                continue
            if info.sample_rate != manifest.audio.sampleRate:
                errors.append(f"{name}: sample rate mismatch")
            if info.channels != manifest.audio.channels:
                errors.append(f"{name}: channel mismatch")
            if info.frames != manifest.audio.frames:
                errors.append(f"{name}: frame mismatch")
            if stem.frames != info.frames:
                errors.append(f"{name}: stem frame metadata mismatch")

    expected_duration = manifest.audio.frames / manifest.audio.sampleRate
    if abs(expected_duration - manifest.audio.durationSeconds) > 1e-6:
        errors.append("audio.durationSeconds does not equal audio.frames / audio.sampleRate")

    if errors:
        raise PackageValidationError(errors)
    return manifest
