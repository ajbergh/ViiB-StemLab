from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

ProgressCallback = Callable[[str, float | None, str | None], None]


@dataclass(frozen=True)
class EngineCapabilities:
    available: bool
    engine: str
    version: str | None
    devices: tuple[str, ...]
    auto_device: str
    detail: str | None = None


@dataclass(frozen=True)
class SeparationResult:
    stems: dict[str, Path]
    engine: str
    model: str
    version: str
    device: str


class StemEngine(Protocol):
    def capabilities(self) -> EngineCapabilities: ...

    def separate(
        self,
        source: Path,
        work_dir: Path,
        *,
        device: str = "auto",
        progress: ProgressCallback | None = None,
    ) -> SeparationResult: ...
