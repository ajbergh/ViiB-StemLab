from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from viib_stemlab.progress import ProgressCallback

if TYPE_CHECKING:
    from viib_stemlab.cancellation import CancellationToken


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
    fallback_occurred: bool = False
    original_device: str | None = None


class StemEngine(Protocol):
    def capabilities(self) -> EngineCapabilities: ...

    def separate(
        self,
        source: Path,
        work_dir: Path,
        *,
        device: str = "auto",
        progress: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        fallback_to_cpu: bool = False,
    ) -> SeparationResult: ...
