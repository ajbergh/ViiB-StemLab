from __future__ import annotations

from pathlib import Path

from viib_stemlab.queue.models import JobRecord, JobStatus
from viib_stemlab.queue.store import QueueStore


def test_queue_store_init(tmp_path: Path) -> None:
    db_file = tmp_path / "test_queue.db"
    store = QueueStore(db_file)
    assert db_file.exists()
    assert store.count_jobs() == 0


def test_add_and_get_job(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    audio_path = tmp_path / "song.wav"
    audio_path.touch()
    out_dir = tmp_path / "stems"

    job = store.add_job(
        source_path=audio_path,
        output_library=out_dir,
        model="htdemucs_6s",
        device="cuda",
        fallback_to_cpu=True,
        overwrite=False,
    )

    assert isinstance(job, JobRecord)
    assert job.status == JobStatus.QUEUED
    assert job.model == "htdemucs_6s"
    assert job.device == "cuda"
    assert job.fallback_to_cpu is True
    assert job.overwrite is False
    assert job.source_path == str(audio_path.resolve())

    fetched = store.get_job(job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.source_path == job.source_path
    assert fetched.created_at == job.created_at


def test_find_jobs_by_source(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    audio1 = tmp_path / "track1.flac"
    audio2 = tmp_path / "track2.flac"
    audio1.touch()
    audio2.touch()

    j1 = store.add_job(audio1, tmp_path / "out")
    j2 = store.add_job(audio2, tmp_path / "out")
    j3 = store.add_job(audio1, tmp_path / "out")

    matches = store.find_jobs_by_source(audio1)
    assert len(matches) == 2
    assert {m.id for m in matches} == {j1.id, j3.id}

    matches2 = store.find_jobs_by_source(audio2)
    assert len(matches2) == 1
    assert matches2[0].id == j2.id


def test_list_and_count_jobs(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    out = tmp_path / "out"

    j1 = store.add_job(tmp_path / "1.wav", out)
    j2 = store.add_job(tmp_path / "2.wav", out)
    store.add_job(tmp_path / "3.wav", out)

    assert store.count_jobs() == 3
    assert store.count_jobs(JobStatus.QUEUED) == 3
    assert store.count_jobs(JobStatus.COMPLETE) == 0

    store.mark_completed(j1.id, out / "pkg1.viibstems")
    assert store.count_jobs(JobStatus.COMPLETE) == 1
    assert store.count_jobs(JobStatus.QUEUED) == 2

    # Limit
    limited = store.list_jobs(limit=2)
    assert len(limited) == 2
    assert limited[0].id == j1.id
    assert limited[1].id == j2.id


def test_get_next_queued_job_fifo(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    j1 = store.add_job(tmp_path / "first.wav", tmp_path / "out")
    j2 = store.add_job(tmp_path / "second.wav", tmp_path / "out")

    next_job = store.get_next_queued_job()
    assert next_job is not None
    assert next_job.id == j1.id

    store.mark_started(j1.id)
    next_job_2 = store.get_next_queued_job()
    assert next_job_2 is not None
    assert next_job_2.id == j2.id


def test_update_progress(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    job = store.add_job(tmp_path / "t.wav", tmp_path / "out")

    store.update_progress(job.id, stage="separating", progress=0.45, message="Separating chunk 3")
    updated = store.get_job(job.id)
    assert updated is not None
    assert updated.status == JobStatus.SEPARATING
    assert updated.stage == "separating"
    assert updated.progress == 0.45
    assert updated.progress_message == "Separating chunk 3"


def test_state_transitions(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    job = store.add_job(tmp_path / "t.wav", tmp_path / "out")

    # Start
    store.mark_started(job.id, actual_device="cpu")
    j_started = store.get_job(job.id)
    assert j_started is not None
    assert j_started.status == JobStatus.PREPARING
    assert j_started.started_at is not None
    assert j_started.actual_device == "cpu"

    # Fail
    store.mark_failed(job.id, error_code="cuda_oom", diagnostic="VRAM exhausted")
    j_failed = store.get_job(job.id)
    assert j_failed is not None
    assert j_failed.status == JobStatus.FAILED
    assert j_failed.error_code == "cuda_oom"
    assert "VRAM exhausted" in (j_failed.diagnostic_message or "")
    assert j_failed.is_terminal is True

    # Retry
    j_retried = store.retry_job(job.id)
    assert j_retried is not None
    assert j_retried.status == JobStatus.QUEUED
    assert j_retried.error_code is None
    assert j_retried.started_at is None

    # Cancel
    store.mark_cancelled(job.id, "Aborted by user")
    j_cancelled = store.get_job(job.id)
    assert j_cancelled is not None
    assert j_cancelled.status == JobStatus.CANCELLED
    assert j_cancelled.error_code == "cancelled"

    # Retry again & Complete
    store.retry_job(job.id)
    pkg_path = tmp_path / "t.viibstems"
    store.mark_completed(job.id, package_path=pkg_path)
    j_completed = store.get_job(job.id)
    assert j_completed is not None
    assert j_completed.status == JobStatus.COMPLETE
    assert j_completed.package_path == str(pkg_path)
    assert j_completed.progress == 1.0


def test_recover_interrupted_jobs(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    j1 = store.add_job(tmp_path / "1.wav", tmp_path / "out")
    j2 = store.add_job(tmp_path / "2.wav", tmp_path / "out")
    j3 = store.add_job(tmp_path / "3.wav", tmp_path / "out")

    # Put j1 in separating and j2 in validating
    store.mark_started(j1.id)
    store.update_progress(j1.id, stage="separating", progress=0.5, message=None)
    store.update_progress(j2.id, stage="validating", progress=0.9, message=None)

    # Recover
    recovered = store.recover_interrupted_jobs()
    assert recovered == 2

    res1 = store.get_job(j1.id)
    assert res1 is not None
    assert res1.status == JobStatus.FAILED
    assert res1.error_code == "worker_crashed"

    res2 = store.get_job(j2.id)
    assert res2 is not None
    assert res2.status == JobStatus.FAILED
    assert res2.error_code == "worker_crashed"

    # j3 is still queued
    res3 = store.get_job(j3.id)
    assert res3 is not None
    assert res3.status == JobStatus.QUEUED


def test_delete_and_clear_jobs(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    j1 = store.add_job(tmp_path / "1.wav", tmp_path / "out")
    j2 = store.add_job(tmp_path / "2.wav", tmp_path / "out")
    j3 = store.add_job(tmp_path / "3.wav", tmp_path / "out")

    assert store.delete_job(j1.id) is True
    assert store.get_job(j1.id) is None
    assert store.count_jobs() == 2

    store.mark_completed(j2.id, tmp_path / "pkg.viibstems")
    # Clear only terminal jobs
    cleared = store.clear_jobs()
    assert cleared == 1
    assert store.get_job(j2.id) is None
    assert store.get_job(j3.id) is not None
