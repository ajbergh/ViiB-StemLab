from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Supported stages of the generation lifecycle
PROGRESS_STAGES = (
    "preflight",
    "preparing",
    "separating",
    "packaging",
    "validating",
    "finalizing",
    "complete",
    "warning",
    "failed",
    "cancelled",
)


@dataclass(frozen=True)
class ProgressUpdate:
    stage: str
    progress: float | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


# Type alias supporting both structured ProgressUpdate and legacy (stage, progress, message) callbacks
ProgressCallback = (
    Callable[[ProgressUpdate], None] | Callable[[str, float | None, str | None], None]
)


class ProgressEmitter:
    """Dispatches progress updates uniformly to either single-arg or 3-arg callback signatures."""

    def __init__(self, callback: ProgressCallback | None = None) -> None:
        self.callback = callback
        self._is_single_arg: bool | None = None
        if callback is not None:
            try:
                sig = inspect.signature(callback)
                # Count positional parameters
                params = [
                    p
                    for p in sig.parameters.values()
                    if p.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                self._is_single_arg = len(params) == 1
            except (ValueError, TypeError):
                self._is_single_arg = None

    def emit(
        self,
        stage: str,
        progress: float | None = None,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.callback is None:
            return

        update = ProgressUpdate(
            stage=stage,
            progress=progress,
            message=message,
            details=details or {},
        )

        if self._is_single_arg is True:
            self.callback(update)  # type: ignore[call-arg]
            return

        if self._is_single_arg is False:
            self.callback(stage, progress, message)  # type: ignore[call-arg]
            return

        # Ambiguous signature (e.g. *args or built-in); try single-arg first, fall back to 3-arg
        try:
            self.callback(update)  # type: ignore[call-arg]
            self._is_single_arg = True
        except TypeError:
            self.callback(stage, progress, message)  # type: ignore[call-arg]
            self._is_single_arg = False
