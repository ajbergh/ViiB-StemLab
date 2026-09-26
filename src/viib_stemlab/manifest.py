"""ViiB Stem Package v1 manifest model.

The field set follows the consumer contract implemented by ViiB MediaHub
(``docs/VIIB_STEM_PACKAGE_V1.md``). StemLab also writes a few optional
extension fields that v1 readers ignore: ``packageId``, ``createdAt``,
``source.sizeBytes``, ``model.engine`` and ``model.device``.

``upgrade_legacy_manifest`` converts manifests written by StemLab 0.1.0, which
predate the contract (``stems.*.file``, ``audio.codec``/``durationSeconds``, no
``stemLayout``/``timing``/per-stem geometry), without touching any audio file.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from viib_stemlab.constants import (
    LAYOUT_STEMS,
    SCHEMA_VERSION,
    SUPPORTED_STEM_ENCODINGS,
)


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _string(obj: dict[str, Any], key: str, parent: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{parent}.{key} must be a string")
    return value


def _optional_string(obj: dict[str, Any], key: str, parent: str) -> str | None:
    if key not in obj or obj[key] is None:
        return None
    return _string(obj, key, parent)


def _integer(obj: dict[str, Any], key: str, parent: str) -> int:
    value = obj.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{parent}.{key} must be an integer")
    return value


def _optional_integer(obj: dict[str, Any], key: str, parent: str) -> int | None:
    if key not in obj or obj[key] is None:
        return None
    return _integer(obj, key, parent)


def _number(obj: dict[str, Any], key: str, parent: str) -> float:
    value = obj.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{parent}.{key} must be a number")
    return float(value)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


@dataclass(frozen=True)
class SourceInfo:
    filename: str
    sha256: str
    duration: float
    # Optional per contract; StemLab does not compute it yet.
    audioSha256: str | None = None
    # StemLab extension: byte size of the source, used for local validation.
    sizeBytes: int | None = None


@dataclass(frozen=True)
class GeneratorInfo:
    name: str
    version: str


@dataclass(frozen=True)
class ModelInfo:
    name: str
    version: str
    # StemLab extensions.
    engine: str | None = None
    device: str | None = None


@dataclass(frozen=True)
class AudioInfo:
    sampleRate: int
    channels: int
    frames: int

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sampleRate if self.sampleRate > 0 else 0.0


@dataclass(frozen=True)
class TimingInfo:
    decoderDelayFrames: int = 0
    startTrimFrames: int = 0


@dataclass(frozen=True)
class StemFileInfo:
    path: str
    sha256: str
    sizeBytes: int
    sampleRate: int
    channels: int
    frames: int
    encoding: str


@dataclass(frozen=True)
class StemManifest:
    schemaVersion: int
    source: SourceInfo
    stemLayout: str
    generator: GeneratorInfo
    model: ModelInfo
    audio: AudioInfo
    timing: TimingInfo
    stems: dict[str, StemFileInfo]
    # StemLab extensions.
    packageId: str | None = None
    createdAt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize in contract field order, omitting unset optional fields."""

        def without_none(values: dict[str, Any]) -> dict[str, Any]:
            return {key: value for key, value in values.items() if value is not None}

        data: dict[str, Any] = {"schemaVersion": self.schemaVersion}
        if self.packageId is not None:
            data["packageId"] = self.packageId
        if self.createdAt is not None:
            data["createdAt"] = self.createdAt
        data["source"] = without_none(
            {
                "filename": self.source.filename,
                "sha256": self.source.sha256,
                "audioSha256": self.source.audioSha256,
                "duration": self.source.duration,
                "sizeBytes": self.source.sizeBytes,
            }
        )
        data["stemLayout"] = self.stemLayout
        data["generator"] = {"name": self.generator.name, "version": self.generator.version}
        data["model"] = without_none(
            {
                "name": self.model.name,
                "version": self.model.version,
                "engine": self.model.engine,
                "device": self.model.device,
            }
        )
        data["audio"] = {
            "sampleRate": self.audio.sampleRate,
            "channels": self.audio.channels,
            "frames": self.audio.frames,
        }
        data["timing"] = {
            "decoderDelayFrames": self.timing.decoderDelayFrames,
            "startTrimFrames": self.timing.startTrimFrames,
        }
        data["stems"] = {
            name: {
                "path": stem.path,
                "sha256": stem.sha256,
                "sizeBytes": stem.sizeBytes,
                "sampleRate": stem.sampleRate,
                "channels": stem.channels,
                "frames": stem.frames,
                "encoding": stem.encoding,
            }
            for name, stem in self.stems.items()
        }
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StemManifest:
        root = _object(data, "manifest")
        for key in ("schemaVersion", "source", "stemLayout", "generator", "model", "audio", "timing", "stems"):
            if key not in root:
                if key in ("stemLayout", "timing") and is_legacy_manifest(root):
                    raise ValueError(
                        f"manifest.{key} is required; this is a StemLab 0.1.0 manifest, "
                        "run `viib-stemlab package upgrade` to convert it to Stem Package v1"
                    )
                raise ValueError(f"manifest.{key} is required")
        source = _object(root.get("source"), "source")
        generator = _object(root.get("generator"), "generator")
        model = _object(root.get("model"), "model")
        audio = _object(root.get("audio"), "audio")
        timing = _object(root.get("timing"), "timing")
        stems_raw = _object(root.get("stems"), "stems")

        stems: dict[str, StemFileInfo] = {}
        for name, raw_entry in stems_raw.items():
            if not isinstance(name, str):
                raise ValueError("stem names must be strings")
            parent = f"stems.{name}"
            entry = _object(raw_entry, parent)
            stems[name] = StemFileInfo(
                path=_string(entry, "path", parent),
                sha256=_string(entry, "sha256", parent),
                sizeBytes=_integer(entry, "sizeBytes", parent),
                sampleRate=_integer(entry, "sampleRate", parent),
                channels=_integer(entry, "channels", parent),
                frames=_integer(entry, "frames", parent),
                encoding=_string(entry, "encoding", parent),
            )

        return cls(
            schemaVersion=_integer(root, "schemaVersion", "manifest"),
            packageId=_optional_string(root, "packageId", "manifest"),
            createdAt=_optional_string(root, "createdAt", "manifest"),
            source=SourceInfo(
                filename=_string(source, "filename", "source"),
                sha256=_string(source, "sha256", "source"),
                duration=_number(source, "duration", "source"),
                audioSha256=_optional_string(source, "audioSha256", "source"),
                sizeBytes=_optional_integer(source, "sizeBytes", "source"),
            ),
            stemLayout=_string(root, "stemLayout", "manifest"),
            generator=GeneratorInfo(
                name=_string(generator, "name", "generator"),
                version=_string(generator, "version", "generator"),
            ),
            model=ModelInfo(
                name=_string(model, "name", "model"),
                version=_string(model, "version", "model"),
                engine=_optional_string(model, "engine", "model"),
                device=_optional_string(model, "device", "model"),
            ),
            audio=AudioInfo(
                sampleRate=_integer(audio, "sampleRate", "audio"),
                channels=_integer(audio, "channels", "audio"),
                frames=_integer(audio, "frames", "audio"),
            ),
            timing=TimingInfo(
                decoderDelayFrames=_integer(timing, "decoderDelayFrames", "timing"),
                startTrimFrames=_integer(timing, "startTrimFrames", "timing"),
            ),
            stems=stems,
        )

    @classmethod
    def from_json(cls, raw: str) -> StemManifest:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("manifest root must be an object")
        return cls.from_dict(parsed)

    @classmethod
    def load(cls, path: Path) -> StemManifest:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def write(self, path: Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    def structural_errors(self) -> list[str]:
        errors: list[str] = []
        if self.schemaVersion != SCHEMA_VERSION:
            errors.append(
                f"unsupported schemaVersion {self.schemaVersion}; expected {SCHEMA_VERSION}"
            )
        if self.packageId is not None and not self.packageId.strip():
            errors.append("packageId must not be empty when present")
        filename = self.source.filename
        if not filename.strip() or "/" in filename or "\\" in filename:
            errors.append("source.filename must be a plain filename")
        if self.source.sizeBytes is not None and self.source.sizeBytes <= 0:
            errors.append("source.sizeBytes must be positive")
        if not _is_sha256(self.source.sha256):
            errors.append("source.sha256 must be a 64-character hexadecimal SHA-256")
        if self.source.audioSha256 is not None and not _is_sha256(self.source.audioSha256):
            errors.append("source.audioSha256 must be a 64-character hexadecimal SHA-256")
        if not self.generator.name.strip() or not self.generator.version.strip():
            errors.append("generator name/version must not be empty")
        if not self.model.name.strip() or not self.model.version.strip():
            errors.append("model name/version must not be empty")
        if self.audio.sampleRate <= 0 or self.audio.channels not in (1, 2) or self.audio.frames <= 0:
            errors.append("audio geometry must be positive with one or two channels")
        if not math.isfinite(self.source.duration) or self.source.duration <= 0:
            errors.append("source.duration must be a finite positive number")
        elif self.audio.sampleRate > 0:
            # Contract: within one sample frame plus 1 ms of frames / sampleRate.
            tolerance = 1 / self.audio.sampleRate + 0.001
            if abs(self.source.duration - self.audio.duration_seconds) > tolerance:
                errors.append("source.duration does not match audio.frames / audio.sampleRate")
        if self.timing.decoderDelayFrames < 0 or self.timing.startTrimFrames < 0:
            errors.append("timing compensation frame counts must not be negative")

        required = LAYOUT_STEMS.get(self.stemLayout)
        if required is None:
            errors.append(f"unsupported stemLayout {self.stemLayout!r}; expected four or six")
        else:
            missing = sorted(set(required) - set(self.stems))
            extra = sorted(set(self.stems) - set(required))
            if missing:
                errors.append(f"missing canonical stems: {', '.join(missing)}")
            if extra:
                errors.append(f"unknown stem entries: {', '.join(extra)}")
        for name, stem in self.stems.items():
            if not stem.path.strip():
                errors.append(f"{name}.path must not be empty")
            if not _is_sha256(stem.sha256):
                errors.append(f"{name}.sha256 must be a 64-character hexadecimal SHA-256")
            if stem.sizeBytes <= 0 or stem.frames <= 0:
                errors.append(f"{name} size/frames must be positive")
            if stem.encoding not in SUPPORTED_STEM_ENCODINGS:
                errors.append(
                    f"{name}.encoding {stem.encoding!r} is not supported; "
                    f"use {' or '.join(SUPPORTED_STEM_ENCODINGS)}"
                )
            if (stem.sampleRate, stem.channels, stem.frames) != (
                self.audio.sampleRate,
                self.audio.channels,
                self.audio.frames,
            ):
                errors.append(f"{name} declared geometry differs from package audio geometry")
        return errors


def is_legacy_manifest(data: dict[str, Any]) -> bool:
    """True for manifests written by StemLab 0.1.0, before the MediaHub contract."""
    if "stemLayout" in data:
        return False
    stems = data.get("stems")
    audio = data.get("audio")
    return (
        isinstance(stems, dict)
        and isinstance(audio, dict)
        and "durationSeconds" in audio
        and all(isinstance(entry, dict) and "file" in entry and "path" not in entry for entry in stems.values())
    )


def upgrade_legacy_manifest(
    data: dict[str, Any],
    stem_formats: dict[str, tuple[int, int, int, str]],
) -> StemManifest:
    """Convert a StemLab 0.1.0 manifest to Stem Package v1.

    ``stem_formats`` maps each stem name to ``(sampleRate, channels, frames,
    encoding)`` read from that stem's WAV header, because 0.1.0 did not record
    per-stem geometry or encoding. Hashes, sizes and paths are carried over
    unchanged; the caller must validate the result against the files.

    Timing is written as zero compensation, which is what 0.1.0 applied: it
    packaged the separator output as-is, without delay compensation or trim.
    """
    if not is_legacy_manifest(data):
        raise ValueError("manifest is not a StemLab 0.1.0 manifest")
    source = _object(data.get("source"), "source")
    generator = _object(data.get("generator"), "generator")
    model = _object(data.get("model"), "model")
    audio = _object(data.get("audio"), "audio")
    stems_raw = _object(data.get("stems"), "stems")

    stem_names = set(stems_raw)
    layout = next((name for name, members in LAYOUT_STEMS.items() if set(members) == stem_names), None)
    if layout is None:
        raise ValueError(f"stem set {sorted(stem_names)} does not match a four- or six-stem layout")

    stems: dict[str, StemFileInfo] = {}
    for name, raw_entry in stems_raw.items():
        entry = _object(raw_entry, f"stems.{name}")
        if name not in stem_formats:
            raise ValueError(f"no WAV format information for stem {name!r}")
        sample_rate, channels, frames, encoding = stem_formats[name]
        stems[name] = StemFileInfo(
            path=_string(entry, "file", f"stems.{name}").replace("\\", "/"),
            sha256=_string(entry, "sha256", f"stems.{name}").lower(),
            sizeBytes=_integer(entry, "sizeBytes", f"stems.{name}"),
            sampleRate=sample_rate,
            channels=channels,
            frames=frames,
            encoding=encoding,
        )

    return StemManifest(
        schemaVersion=_integer(data, "schemaVersion", "manifest"),
        packageId=_optional_string(data, "packageId", "manifest"),
        createdAt=_optional_string(data, "createdAt", "manifest"),
        source=SourceInfo(
            filename=_string(source, "filename", "source"),
            sha256=_string(source, "sha256", "source").lower(),
            duration=_number(audio, "durationSeconds", "audio"),
            sizeBytes=_optional_integer(source, "sizeBytes", "source"),
        ),
        stemLayout=layout,
        generator=GeneratorInfo(
            name=_string(generator, "name", "generator"),
            version=_string(generator, "version", "generator"),
        ),
        model=ModelInfo(
            name=_string(model, "name", "model"),
            version=_string(model, "version", "model"),
            engine=_optional_string(model, "engine", "model"),
            device=_optional_string(model, "device", "model"),
        ),
        audio=AudioInfo(
            sampleRate=_integer(audio, "sampleRate", "audio"),
            channels=_integer(audio, "channels", "audio"),
            frames=_integer(audio, "frames", "audio"),
        ),
        timing=TimingInfo(),
        stems=stems,
    )
