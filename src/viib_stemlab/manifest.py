from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from viib_stemlab.constants import CANONICAL_STEMS, SCHEMA_VERSION


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _string(obj: dict[str, Any], key: str, parent: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{parent}.{key} must be a string")
    return value


def _integer(obj: dict[str, Any], key: str, parent: str) -> int:
    value = obj.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{parent}.{key} must be an integer")
    return value


def _number(obj: dict[str, Any], key: str, parent: str) -> float:
    value = obj.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{parent}.{key} must be a number")
    return float(value)


@dataclass(frozen=True)
class SourceInfo:
    filename: str
    sha256: str
    sizeBytes: int


@dataclass(frozen=True)
class GeneratorInfo:
    name: str
    version: str


@dataclass(frozen=True)
class ModelInfo:
    engine: str
    name: str
    version: str
    device: str


@dataclass(frozen=True)
class AudioInfo:
    codec: str
    sampleRate: int
    channels: int
    frames: int
    durationSeconds: float


@dataclass(frozen=True)
class StemFileInfo:
    file: str
    sha256: str
    sizeBytes: int
    frames: int


@dataclass(frozen=True)
class StemManifest:
    schemaVersion: int
    packageId: str
    createdAt: str
    source: SourceInfo
    generator: GeneratorInfo
    model: ModelInfo
    audio: AudioInfo
    stems: dict[str, StemFileInfo]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StemManifest:
        root = _object(data, "manifest")
        source = _object(root.get("source"), "source")
        generator = _object(root.get("generator"), "generator")
        model = _object(root.get("model"), "model")
        audio = _object(root.get("audio"), "audio")
        stems_raw = _object(root.get("stems"), "stems")

        stems: dict[str, StemFileInfo] = {}
        for name, raw_entry in stems_raw.items():
            if not isinstance(name, str):
                raise ValueError("stem names must be strings")
            entry = _object(raw_entry, f"stems.{name}")
            stems[name] = StemFileInfo(
                file=_string(entry, "file", f"stems.{name}"),
                sha256=_string(entry, "sha256", f"stems.{name}"),
                sizeBytes=_integer(entry, "sizeBytes", f"stems.{name}"),
                frames=_integer(entry, "frames", f"stems.{name}"),
            )

        return cls(
            schemaVersion=_integer(root, "schemaVersion", "manifest"),
            packageId=_string(root, "packageId", "manifest"),
            createdAt=_string(root, "createdAt", "manifest"),
            source=SourceInfo(
                filename=_string(source, "filename", "source"),
                sha256=_string(source, "sha256", "source"),
                sizeBytes=_integer(source, "sizeBytes", "source"),
            ),
            generator=GeneratorInfo(
                name=_string(generator, "name", "generator"),
                version=_string(generator, "version", "generator"),
            ),
            model=ModelInfo(
                engine=_string(model, "engine", "model"),
                name=_string(model, "name", "model"),
                version=_string(model, "version", "model"),
                device=_string(model, "device", "model"),
            ),
            audio=AudioInfo(
                codec=_string(audio, "codec", "audio"),
                sampleRate=_integer(audio, "sampleRate", "audio"),
                channels=_integer(audio, "channels", "audio"),
                frames=_integer(audio, "frames", "audio"),
                durationSeconds=_number(audio, "durationSeconds", "audio"),
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
        if not self.packageId.strip():
            errors.append("packageId must not be empty")
        if not self.createdAt.strip():
            errors.append("createdAt must not be empty")
        if not self.source.filename.strip():
            errors.append("source.filename must not be empty")
        if self.source.sizeBytes <= 0:
            errors.append("source.sizeBytes must be positive")
        if len(self.source.sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.source.sha256
        ):
            errors.append("source.sha256 must be a lowercase 64-character SHA-256")
        if not self.generator.name.strip() or not self.generator.version.strip():
            errors.append("generator name/version must not be empty")
        if (
            not self.model.engine.strip()
            or not self.model.name.strip()
            or not self.model.version.strip()
            or not self.model.device.strip()
        ):
            errors.append("model engine/name/version/device must not be empty")
        if (
            not self.audio.codec.strip()
            or self.audio.sampleRate <= 0
            or self.audio.channels <= 0
            or self.audio.frames <= 0
            or self.audio.durationSeconds <= 0
        ):
            errors.append("audio codec/geometry/duration must be valid and positive")

        expected = set(CANONICAL_STEMS)
        actual = set(self.stems)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            errors.append(f"missing canonical stems: {', '.join(missing)}")
        if extra:
            errors.append(f"unknown stem entries: {', '.join(extra)}")
        for name, stem in self.stems.items():
            if not stem.file.strip():
                errors.append(f"{name}.file must not be empty")
            if len(stem.sha256) != 64 or any(
                char not in "0123456789abcdef" for char in stem.sha256
            ):
                errors.append(f"{name}.sha256 must be a lowercase 64-character SHA-256")
            if stem.sizeBytes <= 0 or stem.frames <= 0:
                errors.append(f"{name} size/frames must be positive")
        return errors
