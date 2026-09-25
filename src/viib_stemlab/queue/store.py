from __future__ import annotations

import os
import platform
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from viib_stemlab.constants import DEFAULT_MODEL
from viib_stemlab.queue.models import JobRecord, JobStatus


def get_default_queue_db_path() -> Path:
    """Resolve the default SQLite database path for the durable queue."""
    custom = os.environ.get("VIIB_STEMLAB_QUEUE_DB")
    if custom:
        return Path(custom)

    app_root = os.environ.get("VIIB_STEMLAB_HOME")
    if app_root:
        return Path(app_root) / "queue.db"

    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
        return base / "ViiB-StemLab" / "queue.db"

    return Path.home() / ".viib-stemlab" / "queue.db"


class QueueStore:
    """Thread-safe and process-safe SQLite store for durable stem generation jobs."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else get_default_queue_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    output_library TEXT NOT NULL,
                    source_hash TEXT,
                    model TEXT NOT NULL,
                    device TEXT NOT NULL,
                    actual_device TEXT,
                    fallback_to_cpu INTEGER NOT NULL DEFAULT 1,
                    overwrite INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    stage TEXT,
                    progress REAL,
                    progress_message TEXT,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    error_code TEXT,
                    diagnostic_message TEXT,
                    package_path TEXT
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source_path ON jobs(source_path);")

    def _row_to_record(self, row: sqlite3.Row) -> JobRecord:
        d: dict[str, Any] = dict(row)
        return JobRecord.from_dict(d)

    def add_job(
        self,
        source_path: Path | str,
        output_library: Path | str,
        *,
        model: str = DEFAULT_MODEL,
        device: str = "auto",
        fallback_to_cpu: bool = True,
        overwrite: bool = False,
        source_hash: str | None = None,
        job_id: str | None = None,
    ) -> JobRecord:
        jid = job_id or str(uuid.uuid4())
        now = time.time()
        record = JobRecord(
            id=jid,
            source_path=str(Path(source_path).resolve()),
            output_library=str(Path(output_library).resolve()),
            source_hash=source_hash,
            model=model,
            device=device,
            fallback_to_cpu=fallback_to_cpu,
            overwrite=overwrite,
            status=JobStatus.QUEUED,
            created_at=now,
        )
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, source_path, output_library, source_hash, model, device,
                    fallback_to_cpu, overwrite, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.source_path,
                    record.output_library,
                    record.source_hash,
                    record.model,
                    record.device,
                    1 if record.fallback_to_cpu else 0,
                    1 if record.overwrite else 0,
                    record.status.value,
                    record.created_at,
                ),
            )
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return self._row_to_record(row) if row else None

    def find_jobs_by_source(self, source_path: Path | str) -> list[JobRecord]:
        resolved = str(Path(source_path).resolve())
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE source_path = ? ORDER BY created_at DESC",
                (resolved,),
            )
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def list_jobs(
        self,
        status: JobStatus | str | None = None,
        limit: int | None = None,
    ) -> list[JobRecord]:
        status_val = status.value if isinstance(status, JobStatus) else status
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if status_val:
            query += " WHERE status = ?"
            params.append(status_val)
        query += " ORDER BY created_at ASC"
        if limit is not None and limit > 0:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def count_jobs(self, status: JobStatus | str | None = None) -> int:
        status_val = status.value if isinstance(status, JobStatus) else status
        query = "SELECT COUNT(*) FROM jobs"
        params: list[Any] = []
        if status_val:
            query += " WHERE status = ?"
            params.append(status_val)
        with self._get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            return int(cursor.fetchone()[0])

    def get_next_queued_job(self) -> JobRecord | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC LIMIT 1",
                (JobStatus.QUEUED.value,),
            )
            row = cursor.fetchone()
            return self._row_to_record(row) if row else None

    def update_progress(
        self,
        job_id: str,
        stage: str | None,
        progress: float | None,
        message: str | None,
    ) -> None:
        status_to_set = None
        if stage in ("preparing", "separating", "packaging", "validating", "finalizing"):
            status_to_set = stage

        with self._get_connection() as conn:
            if status_to_set:
                conn.execute(
                    """
                    UPDATE jobs SET stage = ?, progress = ?, progress_message = ?, status = ?
                    WHERE id = ? AND status NOT IN ('complete', 'failed', 'cancelled')
                    """,
                    (stage, progress, message, status_to_set, job_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs SET stage = ?, progress = ?, progress_message = ?
                    WHERE id = ? AND status NOT IN ('complete', 'failed', 'cancelled')
                    """,
                    (stage, progress, message, job_id),
                )

    def mark_started(self, job_id: str, actual_device: str | None = None) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET status = ?, started_at = ?, actual_device = ?
                WHERE id = ?
                """,
                (JobStatus.PREPARING.value, now, actual_device, job_id),
            )

    def mark_completed(
        self,
        job_id: str,
        package_path: Path | str,
        actual_device: str | None = None,
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    completed_at = ?,
                    package_path = ?,
                    actual_device = COALESCE(?, actual_device),
                    stage = 'complete',
                    progress = 1.0,
                    progress_message = 'Generation completed successfully',
                    error_code = NULL,
                    diagnostic_message = NULL
                WHERE id = ?
                """,
                (JobStatus.COMPLETE.value, now, str(package_path), actual_device, job_id),
            )

    def mark_failed(
        self,
        job_id: str,
        error_code: str,
        diagnostic: str,
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    completed_at = ?,
                    error_code = ?,
                    diagnostic_message = ?
                WHERE id = ?
                """,
                (JobStatus.FAILED.value, now, error_code, diagnostic, job_id),
            )

    def mark_cancelled(self, job_id: str, diagnostic: str | None = None) -> None:
        now = time.time()
        diag = diagnostic or "Job cancelled by user"
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    completed_at = ?,
                    error_code = 'cancelled',
                    diagnostic_message = ?
                WHERE id = ?
                """,
                (JobStatus.CANCELLED.value, now, diag, job_id),
            )

    def retry_job(self, job_id: str) -> JobRecord | None:
        """Reset a failed or cancelled job back to queued status."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    stage = NULL,
                    progress = NULL,
                    progress_message = NULL,
                    started_at = NULL,
                    completed_at = NULL,
                    error_code = NULL,
                    diagnostic_message = NULL,
                    package_path = NULL
                WHERE id = ? AND status IN ('failed', 'cancelled')
                """,
                (JobStatus.QUEUED.value, job_id),
            )
        return self.get_job(job_id)

    def delete_job(self, job_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            return cursor.rowcount > 0

    def clear_jobs(self, status: JobStatus | str | None = None) -> int:
        """Delete jobs by status. If status is None, deletes all terminal jobs."""
        with self._get_connection() as conn:
            if status:
                status_val = status.value if isinstance(status, JobStatus) else status
                cursor = conn.execute("DELETE FROM jobs WHERE status = ?", (status_val,))
            else:
                cursor = conn.execute(
                    "DELETE FROM jobs WHERE status IN ('complete', 'failed', 'cancelled')"
                )
            return cursor.rowcount

    def recover_interrupted_jobs(self) -> int:
        """Transition any orphan in-progress jobs from a previous crash/shutdown to failed."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    completed_at = ?,
                    error_code = 'worker_crashed',
                    diagnostic_message = 'Job was interrupted by unexpected application exit or crash'
                WHERE status IN ('preparing', 'separating', 'packaging', 'validating', 'finalizing')
                """,
                (JobStatus.FAILED.value, now),
            )
            return cursor.rowcount
