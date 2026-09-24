from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from viib_stemlab.constants import CANONICAL_STEMS, DEFAULT_MODEL
from viib_stemlab.engines.base import EngineCapabilities, ProgressCallback, SeparationResult

_PROGRESS = re.compile(r"(\d{1,3})%")


@dataclass(frozen=True)
class TorchRuntimeInfo:
    available: bool
    version: str | None
    cuda_available: bool
    cuda_version: str | None
    mps_available: bool
    detail: str | None = None


class DemucsUnavailableError(RuntimeError):
    pass


def probe_torch_runtime() -> TorchRuntimeInfo:
    if importlib.util.find_spec("torch") is None:
        return TorchRuntimeInfo(
            available=False,
            version=None,
            cuda_available=False,
            cuda_version=None,
            mps_available=False,
            detail="PyTorch is not installed.",
        )

    try:
        import torch
    except Exception as exc:
        return TorchRuntimeInfo(
            available=False,
            version=None,
            cuda_available=False,
            cuda_version=None,
            mps_available=False,
            detail=f"PyTorch import failed: {exc}",
        )

    version = getattr(torch, "__version__", None)
    cuda_version = getattr(getattr(torch, "version", None), "cuda", None)
    details: list[str] = []

    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception as exc:
        cuda_available = False
        details.append(f"CUDA probe failed: {exc}")

    try:
        mps = getattr(torch.backends, "mps", None)
        mps_available = bool(mps is not None and mps.is_available())
    except Exception as exc:
        mps_available = False
        details.append(f"MPS probe failed: {exc}")

    return TorchRuntimeInfo(
        available=True,
        version=str(version) if version is not None else "unknown",
        cuda_available=cuda_available,
        cuda_version=str(cuda_version) if cuda_version is not None else None,
        mps_available=mps_available,
        detail="; ".join(details) or None,
    )


class DemucsEngine:
    name = "demucs"

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model

    def capabilities(self) -> EngineCapabilities:
        if importlib.util.find_spec("demucs") is None:
            return EngineCapabilities(
                available=False,
                engine=self.name,
                version=None,
                devices=("cpu",),
                auto_device="cpu",
                detail='Demucs is not installed. Install the "demucs" extra.',
            )

        try:
            version = metadata.version("demucs")
        except metadata.PackageNotFoundError:
            version = "unknown"

        torch_runtime = probe_torch_runtime()
        if not torch_runtime.available:
            return EngineCapabilities(
                available=False,
                engine=self.name,
                version=version,
                devices=("cpu",),
                auto_device="cpu",
                detail=torch_runtime.detail or "PyTorch is unavailable.",
            )

        devices = ["cpu"]
        auto_device = "cpu"
        if torch_runtime.cuda_available:
            devices.append("cuda")
            auto_device = "cuda"
        if torch_runtime.mps_available:
            devices.append("mps")
            if auto_device == "cpu":
                auto_device = "mps"

        return EngineCapabilities(
            available=True,
            engine=self.name,
            version=version,
            devices=tuple(devices),
            auto_device=auto_device,
            detail=torch_runtime.detail,
        )

    def resolve_device(self, requested: str) -> str:
        caps = self.capabilities()
        if not caps.available:
            raise DemucsUnavailableError(caps.detail or "Demucs is unavailable")
        if requested == "auto":
            return caps.auto_device
        if requested not in {"cpu", "cuda", "mps"}:
            raise ValueError(f"unsupported device: {requested}")
        if requested not in caps.devices:
            raise DemucsUnavailableError(
                f"requested device {requested!r} is unavailable; detected: {', '.join(caps.devices)}"
            )
        return requested

    def separate(
        self,
        source: Path,
        work_dir: Path,
        *,
        device: str = "auto",
        progress: ProgressCallback | None = None,
    ) -> SeparationResult:
        source = Path(source)
        work_dir = Path(work_dir)
        if not source.is_file():
            raise FileNotFoundError(source)

        caps = self.capabilities()
        if not caps.available:
            raise DemucsUnavailableError(caps.detail or "Demucs is unavailable")
        actual_device = self.resolve_device(device)
        work_dir.mkdir(parents=True, exist_ok=True)

        command = [
            sys.executable,
            "-m",
            "demucs.separate",
            "-n",
            self.model,
            "-d",
            actual_device,
            "-o",
            str(work_dir),
            str(source),
        ]

        if progress:
            progress("separating", 0.0, f"Starting Demucs on {actual_device}")

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        tail: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            if line:
                tail.append(line)
                tail = tail[-40:]
            match = _PROGRESS.search(line)
            if match and progress:
                percent = max(0, min(100, int(match.group(1))))
                progress("separating", percent / 100.0, line)

        return_code = process.wait()
        if return_code != 0:
            detail = "\n".join(tail[-15:]) or f"exit status {return_code}"
            raise RuntimeError(f"Demucs separation failed on {actual_device}: {detail}")

        output_dir = work_dir / self.model / source.stem
        stems = {name: output_dir / f"{name}.wav" for name in CANONICAL_STEMS}
        missing = [name for name, path in stems.items() if not path.is_file()]
        if missing:
            raise RuntimeError(
                "Demucs completed but canonical stem output is missing: " + ", ".join(missing)
            )

        if progress:
            progress("separating", 1.0, "Demucs separation complete")

        return SeparationResult(
            stems=stems,
            engine=self.name,
            model=self.model,
            version=caps.version or "unknown",
            device=actual_device,
        )
