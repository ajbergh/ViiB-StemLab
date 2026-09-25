from pathlib import Path

from conftest import FakeEngine

from viib_stemlab.cancellation import CancellationToken
from viib_stemlab.engines.base import EngineCapabilities, SeparationResult
from viib_stemlab.errors import CudaOutOfMemoryError
from viib_stemlab.queue.models import JobStatus
from viib_stemlab.queue.runner import QueueRunner
from viib_stemlab.queue.store import QueueStore


def test_runner_single_job_success(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    store = QueueStore(tmp_path / "queue.db")
    lib_dir = tmp_path / "stems"
    job = store.add_job(source_file, lib_dir)

    completed_jobs = []
    progress_events = []

    runner = QueueRunner(
        store,
        engine=FakeEngine(stem_files),
        on_progress=lambda j, update: progress_events.append((j.id, update.stage)),
        on_job_completed=lambda j: completed_jobs.append(j.id),
    )

    success = runner.run_next()
    assert success is True
    assert len(completed_jobs) == 1
    assert completed_jobs[0] == job.id

    updated = store.get_job(job.id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETE
    assert updated.package_path is not None
    assert Path(updated.package_path).exists()
    assert updated.progress == 1.0
    assert len(progress_events) > 0


def test_runner_batch_run_until_empty(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    store = QueueStore(tmp_path / "queue.db")
    lib_dir = tmp_path / "stems"

    # Add 3 jobs with overwrite so deduplication is allowed
    store.add_job(source_file, lib_dir, overwrite=True)
    store.add_job(source_file, lib_dir, overwrite=True)
    store.add_job(source_file, lib_dir, overwrite=True)

    runner = QueueRunner(store, engine=FakeEngine(stem_files))
    finished = runner.run_until_empty()
    assert finished == 3

    assert store.count_jobs(JobStatus.COMPLETE) == 3
    assert store.count_jobs(JobStatus.QUEUED) == 0


def test_runner_handles_error(
    tmp_path: Path,
    source_file: Path,
) -> None:
    store = QueueStore(tmp_path / "queue.db")
    lib_dir = tmp_path / "stems"
    job = store.add_job(source_file, lib_dir, fallback_to_cpu=False)

    class FailingEngine:
        def capabilities(self) -> EngineCapabilities:
            return EngineCapabilities(
                available=True,
                engine="failing",
                version="1.0",
                devices=("cuda",),
                auto_device="cuda",
            )

        def separate(self, source, work_dir, *, device="auto", progress=None):
            raise CudaOutOfMemoryError("CUDA out of memory during inference")

    failed_jobs = []
    runner = QueueRunner(
        store,
        engine=FailingEngine(),
        on_job_failed=lambda j, err: failed_jobs.append((j.id, err.code)),
    )

    success = runner.run_next()
    assert success is False
    assert len(failed_jobs) == 1
    assert failed_jobs[0][1] == "cuda_oom"

    updated = store.get_job(job.id)
    assert updated is not None
    assert updated.status == JobStatus.FAILED
    assert updated.error_code == "cuda_oom"
    assert "CUDA out of memory" in (updated.diagnostic_message or "")


def test_runner_cancellation(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    store = QueueStore(tmp_path / "queue.db")
    lib_dir = tmp_path / "stems"
    job = store.add_job(source_file, lib_dir)

    class SlowEngine:
        def capabilities(self) -> EngineCapabilities:
            return EngineCapabilities(
                available=True,
                engine="slow",
                version="1.0",
                devices=("cpu",),
                auto_device="cpu",
            )

        def separate(
            self,
            source,
            work_dir,
            *,
            device="auto",
            cancellation_token: CancellationToken | None = None,
            progress=None,
        ):
            if cancellation_token:
                cancellation_token.cancel("User aborted")
                cancellation_token.raise_if_cancelled()
            return SeparationResult(
                stems=stem_files,
                engine="slow",
                model="slow",
                version="1",
                device="cpu",
            )

    runner = QueueRunner(store, engine=SlowEngine())
    success = runner.run_next()
    assert success is False

    updated = store.get_job(job.id)
    assert updated is not None
    assert updated.status == JobStatus.CANCELLED
    assert updated.error_code == "cancelled"


def test_runner_background_worker(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    store = QueueStore(tmp_path / "queue.db")
    lib_dir = tmp_path / "stems"
    store.add_job(source_file, lib_dir, overwrite=True)
    store.add_job(source_file, lib_dir, overwrite=True)

    runner = QueueRunner(store, engine=FakeEngine(stem_files))
    thread = runner.start_background_worker()
    assert thread.is_alive() or store.count_jobs(JobStatus.QUEUED) == 0

    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert store.count_jobs(JobStatus.COMPLETE) == 2
