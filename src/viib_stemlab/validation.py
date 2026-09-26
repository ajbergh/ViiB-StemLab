from __future__ import annotations

import re
import struct
import wave
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from viib_stemlab.constants import PACKAGE_SUFFIX, SUPPORTED_STEM_EXTENSIONS
from viib_stemlab.errors import PackageValidationError
from viib_stemlab.hashing import sha256_file
from viib_stemlab.manifest import StemManifest

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")

_WAVE_FORMAT_PCM = 0x0001
_WAVE_FORMAT_IEEE_FLOAT = 0x0003
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE


@dataclass(frozen=True)
class WavInfo:
    sample_rate: int
    channels: int
    frames: int

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate


@dataclass(frozen=True)
class StemWavFormat:
    sample_rate: int
    channels: int
    frames: int
    encoding: str  # "pcm_s16le" or "float32le"


def read_wav_info(path: Path) -> WavInfo:
    """Geometry of an integer-PCM WAV (used for source preflight)."""
    try:
        with wave.open(str(path), "rb") as reader:
            return WavInfo(
                sample_rate=reader.getframerate(),
                channels=reader.getnchannels(),
                frames=reader.getnframes(),
            )
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"invalid WAV file {path.name}: {exc}") from exc


def read_stem_wav_format(path: Path) -> StemWavFormat:
    """Parse a stem's RIFF/WAVE header and classify its v1 encoding.

    Accepts only what Stem Package v1 allows: PCM 16-bit (``pcm_s16le``) or
    IEEE float 32-bit (``float32le``), mono or stereo, including the
    WAVE_FORMAT_EXTENSIBLE wrapper. Anything else raises ``ValueError``.
    """
    path = Path(path)
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise ValueError(f"{path.name} is not a RIFF/WAVE file")
        fmt: tuple[int, int, int, int, int] | None = None
        data_size: int | None = None
        while True:
            chunk = handle.read(8)
            if len(chunk) < 8:
                break
            chunk_id, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if chunk_id == b"fmt ":
                body = handle.read(size)
                if len(body) < 16:
                    raise ValueError(f"{path.name} fmt chunk is shorter than 16 bytes")
                format_tag, channels, sample_rate, _, block_align, bits = struct.unpack("<HHIIHH", body[:16])
                if format_tag == _WAVE_FORMAT_EXTENSIBLE:
                    if len(body) < 26:
                        raise ValueError(f"{path.name} extensible fmt chunk is truncated")
                    # SubFormat GUID begins with the effective format tag.
                    format_tag = struct.unpack("<H", body[24:26])[0]
                fmt = (format_tag, channels, sample_rate, block_align, bits)
            elif chunk_id == b"data":
                data_size = size
                break
            else:
                handle.seek(size, 1)
            if size % 2:
                handle.seek(1, 1)  # RIFF chunks are word-aligned
    if fmt is None or data_size is None:
        raise ValueError(f"{path.name} is missing a fmt or data chunk")
    format_tag, channels, sample_rate, block_align, bits = fmt
    if format_tag == _WAVE_FORMAT_PCM and bits == 16:
        encoding = "pcm_s16le"
    elif format_tag == _WAVE_FORMAT_IEEE_FLOAT and bits == 32:
        encoding = "float32le"
    else:
        raise ValueError(
            f"{path.name} uses WAV format 0x{format_tag:04x} at {bits} bits; "
            "v1 stems must be PCM16 or float32"
        )
    if channels not in (1, 2) or sample_rate <= 0:
        raise ValueError(f"{path.name} must be mono or stereo with a positive sample rate")
    if block_align != channels * bits // 8 or data_size % block_align:
        raise ValueError(f"{path.name} has an inconsistent WAV block alignment")
    return StemWavFormat(sample_rate=sample_rate, channels=channels, frames=data_size // block_align, encoding=encoding)


def safe_member_path(package_dir: Path, raw: str) -> Path:
    """Resolve a manifest stem path per the v1 path rules."""
    if (
        not raw
        or "\\" in raw
        or "\x00" in raw
        or raw.startswith("/")
        or _WINDOWS_DRIVE.match(raw)
        or any(part in ("", ".", "..") for part in raw.split("/"))
    ):
        raise ValueError(f"unsafe package-relative path: {raw!r}")
    posix = PurePosixPath(raw)
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
    if manifest_path.stat().st_size > 1 << 20:
        raise PackageValidationError(errors + ["manifest.json exceeds 1 MiB"])

    try:
        manifest = StemManifest.load(manifest_path)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise PackageValidationError(errors + [f"manifest is invalid: {exc}"]) from exc

    errors.extend(manifest.structural_errors())

    if source_path is not None:
        source_path = Path(source_path)
        if not source_path.is_file():
            errors.append(f"source file not found: {source_path}")
        else:
            if manifest.source.sizeBytes is not None and source_path.stat().st_size != manifest.source.sizeBytes:
                errors.append("source size does not match manifest")
            if verify_hashes and sha256_file(source_path) != manifest.source.sha256.lower():
                errors.append("source SHA-256 does not match manifest")

    seen: set[Path] = set()
    for name, stem in manifest.stems.items():
        try:
            stem_path = safe_member_path(package_dir, stem.path)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
            continue
        if stem_path.suffix.lower() not in SUPPORTED_STEM_EXTENSIONS:
            errors.append(f"{name}: stem file must be .wav or .wave: {stem.path}")
            continue

        resolved = stem_path.resolve()
        if resolved in seen:
            errors.append(f"{name}: duplicate stem file path {stem.path!r}")
            continue
        seen.add(resolved)

        if not stem_path.is_file():
            errors.append(f"{name}: stem file missing: {stem.path}")
            continue
        if stem_path.stat().st_size != stem.sizeBytes:
            errors.append(
                f"{name}: size mismatch (manifest={stem.sizeBytes}, actual={stem_path.stat().st_size})"
            )
        if verify_hashes and sha256_file(stem_path) != stem.sha256.lower():
            errors.append(f"{name}: SHA-256 mismatch")

        try:
            info = read_stem_wav_format(stem_path)
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        if info.encoding != stem.encoding:
            errors.append(f"{name}: encoding mismatch (manifest={stem.encoding}, file={info.encoding})")
        if info.sample_rate != manifest.audio.sampleRate:
            errors.append(f"{name}: sample rate mismatch")
        if info.channels != manifest.audio.channels:
            errors.append(f"{name}: channel mismatch")
        if info.frames != manifest.audio.frames:
            errors.append(f"{name}: frame mismatch")
        if stem.frames != info.frames:
            errors.append(f"{name}: stem frame metadata mismatch")

    if errors:
        raise PackageValidationError(errors)
    return manifest
