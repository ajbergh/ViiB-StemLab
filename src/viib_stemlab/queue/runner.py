from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from viib_stemlab.cancellation import CancellationToken
from viib_stemlab.errors import GenerationCancelledError, StemLabError, classify_error
from viib_stemlab.progress import ProgressEmitter, ProgressUpdate
from viib_stemlab.queue.models import JobRecord, JobStatus
from viib_stemlab.queue.store import QueueStore
from viib_stemlab.services.generate import generate_package

if TYPE_CHECKING:
    from viib_stemlab.engines.base import StemEngine


class QueueRunner:
    """Orchestrates sequential or worker-driven execution of queued stem generation jobs."""

    def __init__(
        self,
        store: QueueStore,
        *,
        engine: StemEngine | None = None,
        on_progress: Callable[[JobRecord, ProgressUpdate], None] | None = None,
        on_job_completed: Callable[[JobRecord], None] | None = None,
        on_job_failed: Callable[[JobRecord, StemLabError], None] | None = None,
    ) -> None:
        self.store = store
        self.engine = engine
        self.on_progress = on_progress
        self.on_job_completed = on_job_completed
        self.on_job_failed = on_job_failed

        self._active_job_id: str | None = None
        self._active_token: CancellationToken | None = None
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._worker_thread: threading.Thread | None = None

    @property
    def active_job_id(self) -> str | None:
        with self._lock:
            return self._active_job_id

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._worker_thread is not None and self._worker_thread.is_alive()

    def cancel_current_job(self, reason: str = "Job cancelled by user") -> bool:
        """Cancel the currently executing job if one is running."""
        with self._lock:
            if self._active_token is not None:
                self._active_token.cancel(reason)
                return True
        return False

    def cancel_job(self, job_id: str, reason: str = "Job cancelled by user") -> bool:
        """Cancel a job whether it is currently running or waiting in the queue."""
        with self._lock:
            if self._active_job_id == job_id and self._active_token is not None:
                self._active_token.cancel(reason)
                return True

        job = self.store.get_job(job_id)
        if job and job.status == JobStatus.QUEUED:
            self.store.mark_cancelled(job_id, reason)
            return True
        return False

    def run_single_job(self, job: JobRecord) -> bool:
        """Execute a single job through the generation pipeline."""
        with self._lock:
            self._active_job_id = job.id
            token = CancellationToken()
            self._active_token = token

        self.store.mark_started(job.id, actual_device=job.device)

        def _handle_progress(update: ProgressUpdate) -> None:
            self.store.update_progress(
                job.id,
                stage=update.stage,
                progress=update.progress,
                message=update.message,
            )
            if self.on_progress:
                self.on_progress(job, update)

        emitter = ProgressEmitter(_handle_progress)

        engine = self.engine
        if engine is None:
            from viib_stemlab.engines.demucs import DemucsEngine

            engine = DemucsEngine(model=job.model)

        try:
            package_path = generate_package(
                source=Path(job.source_path),
                output_root=Path(job.output_library),
                engine=engine,
                device=job.device,
                fallback_to_cpu=job.fallback_to_cpu,
                overwrite=job.overwrite,
                cancellation_token=token,
                progress=emitter.emit,
            )

            # Determine actual device from manifest if available
            actual_device = job.device
            manifest_file = package_path / "manifest.json"
            if manifest_file.is_file():
                try:
                    data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    actual_device = data.get("model", {}).get("device", actual_device)
                except Exception:
                    pass

            self.store.mark_completed(job.id, package_path, actual_device=actual_device)
            updated_job = self.store.get_job(job.id)
            if updated_job and self.on_job_completed:
                self.on_job_completed(updated_job)
            return True

        except GenerationCancelledError as exc:
            self.store.mark_cancelled(job.id, str(exc))
            return False

        except StemLabError as exc:
            self.store.mark_failed(job.id, exc.code, exc.format_user_message())
            updated_job = self.store.get_job(job.id)
            if updated_job and self.on_job_failed:
                self.on_job_failed(updated_job, exc)
            return False

        except Exception as exc:
            classified = classify_error(exc)
            self.store.mark_failed(job.id, classified.code, classified.format_user_message())
            updated_job = self.store.get_job(job.id)
            if updated_job and self.on_job_failed:
                self.on_job_failed(updated_job, classified)
            return False

        finally:
            with self._lock:
                self._active_job_id = None
                self._active_token = None

    def run_next(self) -> bool:
        """Fetch and execute the next queued job. Returns True if job completed successfully, False otherwise."""
        if self._stop_requested.is_set():
            return False

        job = self.store.get_next_queued_job()
        if not job:
            return False

        return self.run_single_job(job)

    def run_until_empty(
        self,
        *,
        max_jobs: int | None = None,
        recover_orphans: bool = True,
    ) -> int:
        """Synchronously process queued jobs until queue is empty or stop is requested."""
        if recover_orphans:
            self.store.recover_interrupted_jobs()

        self._stop_requested.clear()
        processed_count = 0

        while not self._stop_requested.is_set():
            if max_jobs is not None and processed_count >= max_jobs:
                break

            job = self.store.get_next_queued_job()
            if not job:
                break

            self.run_single_job(job)
            processed_count += 1

        return processed_count

    def request_stop(self) -> None:
        """Request the queue runner to stop after the current job finishes."""
        self._stop_requested.set()

    def start_background_worker(self, *, recover_orphans: bool = True) -> threading.Thread:
        """Launch a background daemon thread that processes queued jobs until empty or stopped."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return self._worker_thread

            self._stop_requested.clear()

            def _worker_loop() -> None:
                self.run_until_empty(recover_orphans=recover_orphans)

            thread = threading.Thread(target=_worker_loop, name="ViiB-QueueWorker", daemon=True)
            self._worker_thread = thread
            thread.start()
            return thread

    def stop_background_worker(self, *, timeout: float = 10.0, cancel_active: bool = False) -> None:
        """Stop background worker thread and optionally cancel the active job."""
        self.request_stop()
        if cancel_active:
            self.cancel_current_job("Queue worker stopped")

        with self._lock:
            thread = self._worker_thread

        if thread and thread.is_alive():
            thread.join(timeout=timeout)
