from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from conftest import write_test_wav

from viib_stemlab.constants import CANONICAL_STEMS, DEFAULT_MODEL
from viib_stemlab.engines.base import EngineCapabilities
from viib_stemlab.engines.demucs import DemucsEngine
from viib_stemlab.errors import CudaOutOfMemoryError
from viib_stemlab.progress import ProgressUpdate


def _caps_with_cuda() -> EngineCapabilities:
    return EngineCapabilities(
        available=True,
        engine="demucs",
        version="4.0.1",
        devices=("cpu", "cuda"),
        auto_device="cuda",
    )


def test_demucs_gpu_oom_without_fallback_raises_error(
    monkeypatch,
    tmp_path: Path,
    source_file: Path,
) -> None:
    engine = DemucsEngine()
    monkeypatch.setattr(engine, "capabilities", _caps_with_cuda)

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.stdout = [
        "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB"
    ]
    fake_process.wait.return_value = 1

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: fake_process)

    with pytest.raises(CudaOutOfMemoryError) as exc_info:
        engine.separate(
            source_file,
            tmp_path / "work",
            device="cuda",
            fallback_to_cpu=False,
        )

    assert exc_info.value.code == "cuda_oom"
    assert "CUDA out of memory" in exc_info.value.message


def test_demucs_gpu_oom_with_fallback_retries_on_cpu(
    monkeypatch,
    tmp_path: Path,
    source_file: Path,
) -> None:
    engine = DemucsEngine()
    monkeypatch.setattr(engine, "capabilities", _caps_with_cuda)

    calls = []

    def fake_popen(cmd, **kwargs):
        device_arg = cmd[cmd.index("-d") + 1]
        calls.append(device_arg)
        proc = MagicMock()
        proc.poll.return_value = None

        if device_arg == "cuda":
            # Simulate OOM on CUDA
            proc.stdout = ["torch.cuda.OutOfMemoryError: CUDA out of memory"]
            proc.wait.return_value = 1
        else:
            # Simulate success on CPU: write expected canonical stems
            out_dir = tmp_path / "work" / DEFAULT_MODEL / source_file.stem
            for stem in CANONICAL_STEMS:
                write_test_wav(out_dir / f"{stem}.wav", frames=64)
            proc.stdout = ["Separating: 100%"]
            proc.wait.return_value = 0
        return proc

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    events: list[ProgressUpdate] = []

    def on_progress(update: ProgressUpdate):
        events.append(update)

    result = engine.separate(
        source_file,
        tmp_path / "work",
        device="cuda",
        fallback_to_cpu=True,
        progress=on_progress,
    )

    # Verifications
    assert calls == ["cuda", "cpu"]
    assert result.device == "cpu"
    assert result.fallback_occurred is True
    assert result.original_device == "cuda"

    # Verify warning progress event was emitted
    warnings = [e for e in events if e.stage == "warning"]
    assert len(warnings) == 1
    assert "Falling back to CPU" in warnings[0].message
    assert warnings[0].details["original_device"] == "cuda"
