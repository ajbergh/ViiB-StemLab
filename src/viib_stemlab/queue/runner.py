from __future__ import annotations

import json
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
    """Orchestrates bounded concurrent execution of queued stem generation jobs."""

    def __init__(
        self,
        store: QueueStore,
        *,
        engine: StemEngine | None = None,
        concurrency: int = 1,
        on_progress: Callable[[JobRecord, ProgressUpdate], None] | None = None,
        on_job_completed: Callable[[JobRecord], None] | None = None,
        on_job_failed: Callable[[JobRecord, StemLabError], None] | None = None,
    ) -> None:
        self.store = store
        self.engine = engine
        self.on_progress = on_progress
        self.on_job_completed = on_job_completed
        self.on_job_failed = on_job_failed

        self._active: dict[str, CancellationToken] = {}
        self._concurrency = 1
        self._lock = threading.Lock()
        self._execution_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self.concurrency = concurrency

    @property
    def active_job_id(self) -> str | None:
        with self._lock:
            return next(iter(self._active), None)

    @property
    def active_job_ids(self) -> list[str]:
        with self._lock:
            return list(self._active)

    @property
    def concurrency(self) -> int:
        with self._lock:
            return self._concurrency

    @concurrency.setter
    def concurrency(self, value: int) -> None:
        if type(value) is not int or value not in (1, 2, 3):
            raise ValueError("Choose 1, 2, or 3 simultaneous songs")
        with self._lock:
            self._concurrency = value

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._worker_thread is not None and self._worker_thread.is_alive()

    def cancel_current_job(self, reason: str = "Job cancelled by user") -> bool:
        """Cancel all currently executing jobs."""
        with self._lock:
            tokens = list(self._active.values())
        for token in tokens:
            token.cancel(reason)
        return bool(tokens)

    def cancel_job(self, job_id: str, reason: str = "Job cancelled by user") -> bool:
        """Cancel one running or queued job without affecting its peers."""
        with self._lock:
            token = self._active.get(job_id)
            if token is None:
                return self.store.cancel_queued_job(job_id, reason)
            token.cancel(reason)
            return True

    def _claim_job(self) -> JobRecord | None:
        # Register cancellation before exposing the claim to API requests.
        with self._lock:
            if self._stop_requested.is_set():
                return None
            job = self.store.claim_next_queued_job()
            if job:
                self._active[job.id] = CancellationToken()
            return job

    def run_single_job(self, job: JobRecord) -> bool:
        """Execute a single job through the generation pipeline."""
        with self._lock:
            token = self._active.setdefault(job.id, CancellationToken())
        if job.status == JobStatus.QUEUED:
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

        try:
            token.raise_if_cancelled()
            engine = self.engine
            if engine is None:
                from viib_stemlab.engines.demucs import DemucsEngine

                engine = DemucsEngine(model=job.model)

            package_path = generate_package(
                source=Path(job.source_path),
                output_root=Path(job.output_library),
                engine=engine,
                device=job.device,
                fallback_to_cpu=job.fallback_to_cpu,
                output_format=job.output_format,
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

            with self._lock:
                token.raise_if_cancelled()
                self.store.mark_completed(job.id, package_path, actual_device=actual_device)
                self._active.pop(job.id, None)
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
                self._active.pop(job.id, None)

    def run_next(self) -> bool:
        """Fetch and execute the next queued job. Returns True if job completed successfully, False otherwise."""
        if not self._execution_lock.acquire(blocking=False):
            raise RuntimeError("Queue is already processing")
        try:
            job = self._claim_job()
            return self.run_single_job(job) if job else False
        finally:
            self._execution_lock.release()

    def run_until_empty(
        self,
        *,
        max_jobs: int | None = None,
        recover_orphans: bool = True,
        _background: bool = False,
    ) -> int:
        """Synchronously process queued jobs until queue is empty or stop is requested."""
        if not self._execution_lock.acquire(blocking=False):
            raise RuntimeError("Queue is already processing")
        try:
            if not _background:
                self._stop_requested.clear()
            if recover_orphans:
                self.store.recover_interrupted_jobs()
            return self._process_queue(max_jobs)
        finally:
            self._execution_lock.release()

    def _process_queue(self, max_jobs: int | None) -> int:
        processed_count = 0
        # Three executor slots allow changing the limit while the queue runs.
        # Lowering the limit lets existing jobs finish before admitting more.
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="ViiB-Song") as pool:
            pending = set()
            try:
                while True:
                    while (
                        not self._stop_requested.is_set()
                        and len(pending) < self.concurrency
                        and (max_jobs is None or processed_count < max_jobs)
                    ):
                        job = self._claim_job()
                        if job is None:
                            break
                        pending.add(pool.submit(self.run_single_job, job))
                        processed_count += 1
                    if not pending:
                        break
                    done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                    for future in done:
                        future.result()
            except BaseException:
                self.request_stop()
                self.cancel_current_job("Queue processing interrupted")
                raise
        return processed_count

    def request_stop(self) -> None:
        """Request the queue runner to stop after the current job finishes."""
        with self._lock:
            self._stop_requested.set()

    def start_background_worker(self, *, recover_orphans: bool = True) -> threading.Thread:
        """Launch a background daemon thread that processes queued jobs until empty or stopped."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return self._worker_thread

            self._stop_requested.clear()

            def _worker_loop() -> None:
                self.run_until_empty(recover_orphans=recover_orphans, _background=True)

            thread = threading.Thread(target=_worker_loop, name="ViiB-QueueWorker", daemon=True)
            self._worker_thread = thread
            thread.start()
            return thread

    def stop_background_worker(self, *, timeout: float = 10.0, cancel_active: bool = False) -> None:
        """Stop admitting jobs and optionally cancel all active jobs."""
        self.request_stop()
        if cancel_active:
            self.cancel_current_job("Queue worker stopped")

        with self._lock:
            thread = self._worker_thread

        if thread and thread.is_alive():
            thread.join(timeout=timeout)
