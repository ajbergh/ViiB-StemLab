from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from conftest import FakeEngine, _caps

from viib_stemlab.cancellation import CancellationToken, cleanup_vram
from viib_stemlab.constants import PACKAGE_SUFFIX
from viib_stemlab.engines.demucs import DemucsEngine
from viib_stemlab.errors import GenerationCancelledError
from viib_stemlab.services.generate import generate_package


def test_cancellation_token_basics() -> None:
    token = CancellationToken()
    assert not token.is_cancelled
    assert token.cancel_reason is None

    token.raise_if_cancelled()  # Should not raise

    callback_called = []
    token.add_callback(lambda: callback_called.append(True))
    assert len(callback_called) == 0

    token.cancel(reason="User stopped generation")
    assert token.is_cancelled
    assert token.cancel_reason == "User stopped generation"
    assert len(callback_called) == 1

    # Adding callback after already cancelled executes immediately
    late_called = []
    token.add_callback(lambda: late_called.append(True))
    assert len(late_called) == 1

    with pytest.raises(GenerationCancelledError, match="User stopped generation"):
        token.raise_if_cancelled()


def test_cancellation_token_multithreaded() -> None:
    token = CancellationToken()
    count = 0
    lock = threading.Lock()

    def cb():
        nonlocal count
        with lock:
            count += 1

    for _ in range(20):
        token.add_callback(cb)

    threads = [
        threading.Thread(target=token.cancel, args=(f"Thread {i}",))
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert token.is_cancelled
    assert count == 20


def test_demucs_engine_cancels_running_subprocess(
    monkeypatch,
    tmp_path: Path,
    source_file: Path,
) -> None:
    engine = DemucsEngine()
    monkeypatch.setattr(engine, "capabilities", lambda: _caps("cpu"))

    token = CancellationToken()
    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.stdout = ["Separating: 10%", "Separating: 20%"]
    fake_process.wait.return_value = 0

    def fake_popen(*args, **kwargs):
        # Cancel token during process execution
        token.cancel(reason="Simulated user abort")
        return fake_process

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    with pytest.raises(GenerationCancelledError, match="Simulated user abort"):
        engine.separate(
            source_file,
            tmp_path / "work",
            device="cpu",
            cancellation_token=token,
        )

    # Verify process was terminated
    assert fake_process.terminate.called or fake_process.kill.called


def test_generate_package_cleans_up_staging_on_cancellation(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    output_library = tmp_path / "library"
    output_library.mkdir(parents=True, exist_ok=True)
    token = CancellationToken()

    class CancellingEngine(FakeEngine):
        def separate(self, source, work_dir, **kwargs):
            # Simulate cancellation while engine is separating
            token.cancel("Cancelled mid-separation")
            raise GenerationCancelledError("Cancelled mid-separation")

    engine = CancellingEngine(stem_files)

    with pytest.raises(GenerationCancelledError, match="Cancelled mid-separation"):
        generate_package(
            source=source_file,
            output_root=output_library,
            engine=engine,
            cancellation_token=token,
            skip_preflight=True,
        )

    # Verify no .partial directories or completed packages remain
    partial_dirs = list(output_library.glob(".*partial*"))
    assert len(partial_dirs) == 0
    package_dirs = list(output_library.glob(f"*{PACKAGE_SUFFIX}"))
    assert len(package_dirs) == 0
