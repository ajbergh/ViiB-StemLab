"""Validated, atomic desktop preferences shared by UI and queue ingestion."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from viib_stemlab.constants import DEFAULT_MODEL


class SettingsStore:
    def __init__(self, path: Path, library: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._values: dict[str, Any] = {
            "library_path": library,
            "model": DEFAULT_MODEL,
            "device": "auto",
            "fallback_to_cpu": True,
            "auto_cuda": True,
            "output_format": "wav",
            "concurrency": 1,
        }
        if path.is_file():
            values = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(values, dict) and values.get("model") == "htdemucs_6s":
                values["model"] = DEFAULT_MODEL
            self._validate(values)
            self._values.update(values)

    @staticmethod
    def _validate(values: dict[str, Any]) -> None:
        if not isinstance(values, dict) or set(values) - {
            "library_path", "model", "device", "fallback_to_cpu", "auto_cuda", "output_format", "concurrency"
        }:
            raise ValueError("Unknown settings")
        if "concurrency" in values and (type(values["concurrency"]) is not int or values["concurrency"] not in (1, 2, 3)):
            raise ValueError("Choose 1, 2, or 3 simultaneous songs")
        if "model" in values and values["model"] != DEFAULT_MODEL:
            raise ValueError("Choose htdemucs_ft for four-stem generation")
        if "output_format" in values and values["output_format"] not in ("wav", "ogg", "mp3"):
            raise ValueError("Choose wav, ogg, or mp3 for output_format")
        if "device" in values and values["device"] not in ("auto", "cpu", "cuda", "mps"):
            raise ValueError("Unknown compute device")
        if "fallback_to_cpu" in values and not isinstance(values["fallback_to_cpu"], bool):
            raise ValueError("fallback_to_cpu must be a boolean")
        if "auto_cuda" in values and not isinstance(values["auto_cuda"], bool):
            raise ValueError("auto_cuda must be a boolean")
        if "library_path" in values and (
            not isinstance(values["library_path"], str)
            or not values["library_path"].strip()
            or not Path(values["library_path"]).is_absolute()
        ):
            raise ValueError("Choose an absolute output library path")

    def get(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._values)

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        self._validate(values)
        with self._lock:
            updated = self._values | values
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(updated, stream, indent=2)
                os.replace(name, self.path)
            finally:
                Path(name).unlink(missing_ok=True)
            self._values = updated
            return dict(updated)
