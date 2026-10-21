from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from viib_stemlab.cancellation import CancellationToken, cleanup_vram
from viib_stemlab.constants import CANONICAL_STEMS, DEFAULT_MODEL
from viib_stemlab.engines.base import EngineCapabilities, SeparationResult
from viib_stemlab.errors import (
    CudaOutOfMemoryError,
    CudaUnavailableError,
    DemucsUnavailableError,
    InferenceFailedError,
    MpsUnavailableError,
    OutputMissingError,
    WorkerCrashedError,
    classify_process_failure,
)
from viib_stemlab.models import ModelCacheManager
from viib_stemlab.progress import ProgressCallback, ProgressEmitter

_PROGRESS = re.compile(r"(\d{1,3})%")


def demucs_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--demucs-worker"]
    return [sys.executable, "-m", "demucs.separate"]


@dataclass(frozen=True)
class TorchRuntimeInfo:
    available: bool
    version: str | None
    cuda_available: bool
    cuda_version: str | None
    mps_available: bool
    detail: str | None = None


def _stop_process(
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float = 5.0,
) -> None:
    """Terminate an owned Demucs subprocess and escalate to kill if needed."""
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)


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

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        cache_dir: Path | None = None,
    ) -> None:
        self.model = model
        self.cache_dir = cache_dir

    def worker_command(self, device: str) -> list[str]:
        from viib_stemlab.cuda_runtime import get_cuda_worker

        worker = get_cuda_worker() if device == "cuda" else None
        return [str(worker), "--demucs-worker"] if worker else demucs_command()

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
        from viib_stemlab.cuda_runtime import get_cuda_worker

        if torch_runtime.cuda_available or get_cuda_worker() is not None:
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
            if requested == "cuda":
                raise CudaUnavailableError(
                    "CUDA is not ready. Open Settings to install NVIDIA acceleration or choose Auto/CPU. "
                    f"Detected: {', '.join(caps.devices)}"
                )
            if requested == "mps":
                raise MpsUnavailableError(
                    f"requested device 'mps' is unavailable; detected: {', '.join(caps.devices)}"
                )
            raise DemucsUnavailableError(
                f"requested device {requested!r} is unavailable; detected: {', '.join(caps.devices)}"
            )
        return requested

    def _execute_subprocess(
        self,
        command: list[str],
        actual_device: str,
        emitter: ProgressEmitter,
        cancellation_token: CancellationToken | None,
        env: dict[str, str],
    ) -> None:
        from viib_stemlab.cuda_runtime import spawn_worker, worker_environment

        process = spawn_worker(
            command,
            # Never inherit the launcher's lifetime pipe. On Windows an active
            # read in the parent can block child stdio initialization on it.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=worker_environment(env),
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )

        # Register token cancellation handler to terminate subprocess immediately
        if cancellation_token:
            cancellation_token.add_callback(lambda: _stop_process(process))

        tail: list[str] = []
        assert process.stdout is not None
        try:
            for line in process.stdout:
                if cancellation_token and cancellation_token.is_cancelled:
                    _stop_process(process)
                    cleanup_vram()
                    cancellation_token.raise_if_cancelled()

                line = line.rstrip()
                if line:
                    tail.append(line)
                    tail = tail[-40:]
                match = _PROGRESS.search(line)
                if match:
                    percent = max(0, min(100, int(match.group(1))))
                    emitter.emit("separating", percent / 100.0, line)

            return_code = process.wait()
        except KeyboardInterrupt:
            _stop_process(process)
            cleanup_vram()
            raise
        except BaseException:
            _stop_process(process)
            cleanup_vram()
            raise
        finally:
            close_stdout = getattr(process.stdout, "close", None)
            if callable(close_stdout):
                close_stdout()

        if cancellation_token and cancellation_token.is_cancelled:
            cleanup_vram()
            cancellation_token.raise_if_cancelled()

        if return_code != 0:
            cleanup_vram()
            structured_error = classify_process_failure(return_code, tail, actual_device)
            raise structured_error

    def separate(
        self,
        source: Path,
        work_dir: Path,
        *,
        device: str = "auto",
        progress: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        fallback_to_cpu: bool = False,
    ) -> SeparationResult:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()

        source = Path(source)
        work_dir = Path(work_dir)
        if not source.is_file():
            raise FileNotFoundError(source)

        caps = self.capabilities()
        if not caps.available:
            raise DemucsUnavailableError(caps.detail or "Demucs is unavailable")

        resolution_fallback = False
        try:
            actual_device = self.resolve_device(device)
        except (CudaUnavailableError, MpsUnavailableError):
            if not fallback_to_cpu:
                raise
            actual_device = "cpu"
            resolution_fallback = True
        work_dir.mkdir(parents=True, exist_ok=True)
        emitter = ProgressEmitter(progress)
        if resolution_fallback:
            emitter.emit("warning", None, f"{device.upper()} is unavailable. Falling back to CPU.")

        # Prepare environment with TORCH_HOME if model cache dir configured
        env = dict(os.environ)
        if getattr(sys, "frozen", False):
            # This is an independent frozen invocation, not a multiprocessing
            # continuation. Reset the bootloader's inherited process state.
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        if self.cache_dir:
            mgr = ModelCacheManager(self.cache_dir)
            env["TORCH_HOME"] = str(mgr.get_torch_home())

        command = [
            *self.worker_command(actual_device),
            "-n",
            self.model,
            "-d",
            actual_device,
            "-o",
            str(work_dir),
            str(source),
        ]

        emitter.emit("separating", 0.0, f"Starting Demucs on {actual_device}")

        fallback_occurred = resolution_fallback
        original_device: str | None = device if resolution_fallback else None

        try:
            self._execute_subprocess(
                command,
                actual_device,
                emitter,
                cancellation_token,
                env,
            )
        except (CudaOutOfMemoryError, CudaUnavailableError, MpsUnavailableError,
                InferenceFailedError, WorkerCrashedError) as exc:
            if not fallback_to_cpu or actual_device == "cpu":
                raise

            # Explicit GPU-to-CPU fallback policy
            fallback_occurred = True
            original_device = actual_device
            emitter.emit(
                "warning",
                None,
                f"GPU execution failed on {actual_device} ({exc.code}): {exc.message}. Falling back to CPU.",
                details={"original_device": actual_device, "reason": exc.code},
            )
            cleanup_vram()

            cpu_command = [
                *demucs_command(),
                "-n",
                self.model,
                "-d",
                "cpu",
                "-o",
                str(work_dir),
                str(source),
            ]
            emitter.emit("separating", 0.0, "Restarting Demucs separation on CPU")
            self._execute_subprocess(
                cpu_command,
                "cpu",
                emitter,
                cancellation_token,
                env,
            )
            actual_device = "cpu"

        output_dir = work_dir / self.model / source.stem
        stems = {name: output_dir / f"{name}.wav" for name in CANONICAL_STEMS}
        missing = [name for name, path in stems.items() if not path.is_file()]
        if missing:
            raise OutputMissingError(
                "Demucs completed but canonical stem output is missing: " + ", ".join(missing),
                details={"missing_stems": missing},
            )

        emitter.emit("separating", 1.0, "Demucs separation complete")

        return SeparationResult(
            stems=stems,
            engine=self.name,
            model=self.model,
            version=caps.version or "unknown",
            device=actual_device,
            fallback_occurred=fallback_occurred,
            original_device=original_device,
        )
