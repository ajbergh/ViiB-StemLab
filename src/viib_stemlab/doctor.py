"""System capabilities, runtime probing, and environment diagnostics for ViiB-StemLab."""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path
from shutil import which
from typing import Any

from viib_stemlab import __version__
from viib_stemlab.constants import SUPPORTED_INPUT_EXTENSIONS
from viib_stemlab.engines.demucs import DemucsEngine, probe_torch_runtime
from viib_stemlab.models import ModelCacheManager


def get_doctor_report(cwd: Path | None = None) -> dict[str, Any]:
    """Compile diagnostic status of PyTorch, CUDA/MPS, Demucs, FFmpeg, and model caches."""
    caps = DemucsEngine().capabilities()
    torch_runtime = probe_torch_runtime()
    cache_mgr = ModelCacheManager()
    cached_models = cache_mgr.list_known_models()
    disk_target = cwd or Path.cwd()
    disk_usage = shutil.disk_usage(disk_target)

    return {
        "stemLabVersion": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "torch": {
            "available": torch_runtime.available,
            "version": torch_runtime.version,
            "cudaAvailable": torch_runtime.cuda_available,
            "cudaRuntime": torch_runtime.cuda_version,
            "mpsAvailable": torch_runtime.mps_available,
            "detail": torch_runtime.detail,
        },
        "demucs": {
            "available": caps.available,
            "version": caps.version,
            "devices": list(caps.devices),
            "autoDevice": caps.auto_device,
            "detail": caps.detail,
        },
        "input": {
            "extensions": list(SUPPORTED_INPUT_EXTENSIONS),
            "ffmpegAvailable": which("ffmpeg") is not None,
            "ffprobeAvailable": which("ffprobe") is not None,
        },
        "modelCache": {
            "directory": str(cache_mgr.cache_dir),
            "models": [m.to_dict() for m in cached_models],
        },
        "disk": {
            "target": str(disk_target),
            "totalBytes": disk_usage.total,
            "freeBytes": disk_usage.free,
            "freeGb": round(disk_usage.free / (1024**3), 2),
        },
    }
