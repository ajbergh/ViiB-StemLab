# Phase 4A — Durable Queue & Batch Engine Reference

**Status:** Complete — 2026-09-25  
**Deliverables:** SQLite WAL QueueStore, Batch Track Discovery & Deduplication, QueueRunner Coordinator, Crash Recovery, CLI Suite  
**Test Suite:** 84 passing unit & integration tests (`uv run pytest`)

## Overview
Phase 4A introduces a headless, resilient batch ingestion and queue processing engine to **ViiB-StemLab**. It decouples track discovery and preparation scheduling from active processing, enabling users to queue entire directories of audio files, monitor background progress, pause/cancel/retry jobs, recover from unexpected shutdowns, and safely process workloads without GPU memory exhaustion or data loss.

---

## Architecture & Components

```
+------------------------------------------------------------------------+
|                          Batch Ingestion                               |
|   (discover_audio_files, find_existing_package_for_source, ingest_paths)|
+------------------------------------+-----------------------------------+
                                     |
                                     v
+------------------------------------------------------------------------+
|                        QueueStore (SQLite WAL)                         |
|   schema: jobs (id, source_path, output_lib, status, error, ...)       |
|   WAL mode, crash recovery, FIFO ordering, thread-safe mutations       |
+------------------------------------+-----------------------------------+
                                     ^
                                     |  pop / update / complete
+------------------------------------+-----------------------------------+
|                        QueueRunner & Worker                            |
|   - Sequential FIFO loop / Background Daemon Thread                    |
|   - CancellationToken binding & process isolation                      |
|   - Real-time progress forwarding (store.update_progress)              |
|   - Error taxonomy classification (store.mark_failed)                  |
|   - Crash recovery on boot (recover_interrupted_jobs)                  |
+------------------------------------------------------------------------+
```

---

## 1. Durable Storage & Schema (`QueueStore`)

### Database Location Resolution
The queue SQLite database path is resolved using the following priority order:
1. Explicit `--db <path>` flag or constructor argument `QueueStore(db_path)`.
2. Environment variable `VIIB_STEMLAB_QUEUE_DB`.
3. Application home `VIIB_STEMLAB_HOME / "queue.db"`.
4. Platform standard app data directory:
   - **Windows**: `%LOCALAPPDATA%\ViiB-StemLab\queue.db`
   - **macOS**: `~/Library/Application Support/ViiB-StemLab/queue.db`
   - **Linux**: `~/.local/share/viib-stemlab/queue.db` (or `~/.viib-stemlab/queue.db`)

### SQLite Configuration
- **WAL Mode**: Executed with `PRAGMA journal_mode=WAL;` and `PRAGMA synchronous=NORMAL;` on connection to allow concurrent reads and writes without database locking.
- **Foreign Keys & Indices**: Indexed on `(status, created_at)` for instant FIFO job retrieval and on `(source_path)` for rapid deduplication checks.

### Schema Definition
```sql
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
```

---

## 2. Job State Lifecycle & Transitions

```
                    +------------------------+
                    |        QUEUED          |
                    +-----------+------------+
                                |
                                v
                    +------------------------+
                    |       PREPARING        |<----+ (retry_job)
                    +-----------+------------+     |
                                |                  |
                                v                  |
                    +------------------------+     |
                    |       SEPARATING       |     |
                    +-----------+------------+     |
                                |                  |
                                v                  |
                    +------------------------+     |
                    |       PACKAGING        |     |
                    +-----------+------------+     |
                                |                  |
                                v                  |
                    +------------------------+     |
                    |       VALIDATING       |     |
                    +-----------+------------+     |
                                |                  |
                                v                  |
                    +------------------------+     |
                    |       FINALIZING       |     |
                    +-----------+------------+     |
                                |                  |
            +-------------------+------------------+----+
            |                   |                       |
            v                   v                       v
    +---------------+   +---------------+       +---------------+
    |   COMPLETE    |   |    FAILED     |       |   CANCELLED   |
    +---------------+   +-------+-------+       +-------+-------+
                                |                       |
                                +-----------------------+
```

### Crash Recovery
If the process terminates unexpectedly while a job is in an active state (`PREPARING`, `SEPARATING`, `PACKAGING`, `VALIDATING`, `FINALIZING`), calling `QueueStore.recover_interrupted_jobs()` resets those orphan jobs to `JobStatus.FAILED` with error code `worker_crashed` and a descriptive message. This prevents hanging zombie jobs on next launch.

---

## 3. Audio File Discovery & Batch Ingestion

### Supported Formats
Supports `.wav`, `.flac`, `.mp3`, and `.ogg` case-insensitively.

### Deduplication Rules
When scanning paths with `ingest_paths()`:
1. **Existing Queue Jobs**: If a job for the same audio source file is already `QUEUED`, active, or `COMPLETE` (and `--overwrite` is not requested), the file is skipped (`skipped_duplicate_queue`).
2. **Existing Stem Packages**: If an existing `.viibstems` package exists in the target output library matching the track name and manifest, the file is skipped (`skipped_existing_package`).
3. **Overwrite Mode**: When `--overwrite` is specified, duplicates and existing packages are queued for re-generation.

---

## 4. Execution Coordinator (`QueueRunner`)

- **Sequential Execution**: Protects GPU VRAM by executing heavy separation tasks sequentially.
- **Cancellation Token Binding**: Attaches a `CancellationToken` to every job run. Calling `cancel_current_job()` or `cancel_job(id)` immediately cancels the subprocess, terminates Demucs, and invokes `cleanup_vram()`.
- **Live Progress Forwarding**: Generation callbacks directly update the job's progress percentage and stage in SQLite, making state inspectable by external consumers or UIs.
- **Background Daemon Worker**: `start_background_worker()` spins up a background thread that monitors and executes the queue to completion.

---

## 5. CLI Command Reference

### `viib-stemlab queue add`
Adds tracks or directories to the processing queue.
```bash
viib-stemlab queue add /path/to/album/ --output /path/to/ViiB-Library/
viib-stemlab queue add track1.flac track2.wav --output /stems --model htdemucs_6s --fallback-to-cpu
```

### `viib-stemlab queue list`
Lists all jobs or filters by status. Supports JSON output for GUI integration.
```bash
viib-stemlab queue list
viib-stemlab queue list --status queued
viib-stemlab queue list --json
```

### `viib-stemlab queue start`
Starts sequential queue processing until empty. Gracefully stops and cleans up upon Ctrl+C (`SIGINT`).
```bash
viib-stemlab queue start
viib-stemlab queue start --max-jobs 5
```

### `viib-stemlab queue cancel`
Cancels an active or queued job.
```bash
viib-stemlab queue cancel <job_id> --reason "User requested stop"
```

### `viib-stemlab queue retry`
Resets a failed or cancelled job back to `QUEUED`.
```bash
viib-stemlab queue retry <job_id>
```

### `viib-stemlab queue remove`
Removes a specific job from the queue database.
```bash
viib-stemlab queue remove <job_id>
```

### `viib-stemlab queue clear`
Clears completed, failed, or cancelled jobs from the queue database.
```bash
viib-stemlab queue clear
viib-stemlab queue clear --status complete
```
