from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from viib_stemlab.constants import CANONICAL_STEMS, SCHEMA_VERSION


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
    def from_dict(cls, data: dict[str, Any]) -> "StemManifest":
        stems_raw = data["stems"]
        if not isinstance(stems_raw, dict):
            raise ValueError("stems must be an object")
        return cls(
            schemaVersion=data["schemaVersion"],
            packageId=data["packageId"],
            createdAt=data["createdAt"],
            source=SourceInfo(**data["source"]),
            generator=GeneratorInfo(**data["generator"]),
            model=ModelInfo(**data["model"]),
            audio=AudioInfo(**data["audio"]),
            stems={name: StemFileInfo(**entry) for name, entry in stems_raw.items()},
        )

    @classmethod
    def from_json(cls, raw: str) -> "StemManifest":
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("manifest root must be an object")
        return cls.from_dict(parsed)

    @classmethod
    def load(cls, path: Path) -> "StemManifest":
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
        if len(self.source.sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.source.sha256
        ):
            errors.append("source.sha256 must be a lowercase 64-character SHA-256")
        if self.audio.sampleRate <= 0 or self.audio.channels <= 0 or self.audio.frames <= 0:
            errors.append("audio geometry must be positive")
        expected = set(CANONICAL_STEMS)
        actual = set(self.stems)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            errors.append(f"missing canonical stems: {', '.join(missing)}")
        if extra:
            errors.append(f"unknown stem entries: {', '.join(extra)}")
        for name, stem in self.stems.items():
            if len(stem.sha256) != 64 or any(
                char not in "0123456789abcdef" for char in stem.sha256
            ):
                errors.append(f"{name}.sha256 must be a lowercase 64-character SHA-256")
            if stem.sizeBytes <= 0 or stem.frames <= 0:
                errors.append(f"{name} size/frames must be positive")
        return errors
