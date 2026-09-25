from __future__ import annotations

import contextlib
import sys
import threading
from collections.abc import Callable

from viib_stemlab.errors import GenerationCancelledError


class CancellationToken:
    """Thread-safe cancellation token for cooperative job cancellation."""

    def __init__(self) -> None:
        self._is_cancelled = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []
        self._reason: str | None = None

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled.is_set()

    @property
    def cancel_reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str = "Job cancelled by user") -> None:
        """Signal cancellation and invoke any registered callbacks immediately."""
        to_run: list[Callable[[], None]] = []
        with self._lock:
            if self._is_cancelled.is_set():
                return
            self._reason = reason
            self._is_cancelled.set()
            to_run = list(self._callbacks)
            self._callbacks.clear()

        for callback in to_run:
            with contextlib.suppress(Exception):
                callback()

    def add_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be executed upon cancellation, or immediately if already cancelled."""
        with self._lock:
            if self._is_cancelled.is_set():
                already_cancelled = True
            else:
                self._callbacks.append(callback)
                already_cancelled = False

        if already_cancelled:
            with contextlib.suppress(Exception):
                callback()

    def raise_if_cancelled(self) -> None:
        """Raise GenerationCancelledError if the token has been cancelled."""
        if self._is_cancelled.is_set():
            raise GenerationCancelledError(self._reason or "Job cancelled")


def cleanup_vram() -> None:
    """Best-effort release of GPU VRAM if PyTorch is loaded in the host process."""
    if "torch" in sys.modules:
        with contextlib.suppress(Exception):
            import torch

            if hasattr(torch, "cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
