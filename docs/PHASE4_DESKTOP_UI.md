# Phase 4B: Desktop UI Shell (React + Tauri)

> **Status**: Completed (2026-09-25)  
> **Backend Verification**: 89/89 Python unit & integration tests passing  
> **Frontend Verification**: 4/4 Vitest unit tests passing, clean Vite build (`desktop/dist/`)  
> **Reference Design**: Consistent with `ViiB-MediaHub` (Tailwind dark DJ surface palette, Lucide icons, responsive layout)

---

## 1. Architectural Overview

Phase 4B provides the desktop user interface shell for ViiB-StemLab. Built upon the durable SQLite WAL queue engine and headless coordinator from Phase 4A, it enables non-CLI users to drag-and-drop tracks, monitor multi-stage AI stem separation, inspect completed `.viibstems` packages, and diagnose hardware acceleration.

```
+-----------------------------------------------------------------------------------+
|                            ViiB StemLab Desktop Shell                             |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                 React 19 + TypeScript + Vite + Tailwind CSS                 |  |
|  |                                                                             |  |
|  |  [ Navbar: Brand, Navigation Tabs, Live Background Worker Status ]          |  |
|  |                                                                             |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  |  | Views:                                                                |  |  |
|  |  | 1. QueueView: KPI cards, DropZone, batch controls, live job list      |  |  |
|  |  | 2. LibraryView: Completed .viibstems packages, stem cards, validator |  |  |
|  |  | 3. SettingsDoctorView: Library path, model picker, device, diagnostics|  |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|                  REST API over HTTP (JSON / localhost:8765)                       |
|                                         v                                         |
|  +-----------------------------------------------------------------------------+  |
|  |                        Python UI Server & Runner                            |  |
|  |                  (src/viib_stemlab/ui/server.py)                            |  |
|  |                                                                             |  |
|  |  * Zero external web framework dependencies (built on ThreadingHTTPServer)  |  |
|  |  * Built-in CORS support for development                                   |  |
|  |  * Static SPA hosting with fallback to desktop/dist/index.html              |  |
|  |  * Direct integration with QueueStore, QueueRunner, & Doctor               |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|                   Tauri v2 Native Window Wrapper (desktop/src-tauri)               |
+-----------------------------------------------------------------------------------+
```

---

## 2. Python UI Backend (`src/viib_stemlab/ui/server.py`)

The UI backend requires **zero third-party web frameworks** (no FastAPI, Flask, Starlette, or Uvicorn). It extends the standard library `http.server.ThreadingHTTPServer` to handle concurrent API requests and static single-page application delivery safely across worker threads.

### REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check endpoint returning server status and version. |
| `GET` | `/api/queue` | Returns all jobs (optionally filtered by `?status=`), summary KPI counts, worker running status, and active job ID. |
| `POST` | `/api/queue/add` | Ingests audio files/directories with deduplication and validation. |
| `POST` | `/api/queue/start` | Starts the background queue worker thread. |
| `POST` | `/api/queue/stop` | Stops the background worker thread (optionally cancelling the active job). |
| `POST` | `/api/queue/cancel` | Cancels a specific job (active or queued). |
| `POST` | `/api/queue/retry` | Resets a failed or cancelled job back to queued status. |
| `POST` | `/api/queue/remove` | Removes a completed, failed, or cancelled job from the queue. |
| `POST` | `/api/queue/clear` | Purges completed or failed jobs from the queue store. |
| `GET` | `/api/doctor` | Returns full runtime environment diagnostic metrics from `get_doctor_report()`. |
| `GET` | `/api/models` | Lists Demucs models, cache paths, local status, and file sizes. |
| `POST` | `/api/models/download` | Triggers background pre-download of model weights into PyTorch hub checkpoints. |
| `GET` | `/api/library` | Scans a target stem library directory for `.viibstems` packages and metadata. |
| `POST` | `/api/package/validate` | Validates an existing `.viibstems` package against the v1 specification. |
| `GET` | `/*` | Static file handler serving `desktop/dist/` assets with automatic fallback to `index.html` for client-side routing. Prevents directory traversal attacks. |

---

## 3. Frontend Architecture (`desktop/`)

The desktop frontend is structured for modularity and performance:

- **Build Stack**: Vite 6, React 19, TypeScript 5.8, Tailwind CSS 3.4, PostCSS, Lucide React.
- **Design System**: Matches `ViiB-MediaHub`:
  - `surface-0` (`#0B0B0E`), `surface-1` (`#121216`), `surface-2` (`#18181E`), `surface-3` (`#24242B`)
  - Accent colors: `brand` (`#9B5CFF`), `accent-green` (`#3EE089`), `accent-orange` (`#FF9F43`), `accent-blue` (`#4EA1FF`), `accent-crimson` (`#FF5D5D`).
- **Core Views**:
  1. **QueueView**:
     - KPI summary cards (Total, Queued, Processing, Completed, Failed).
     - Drag-and-drop dropzone supporting high-resolution WAV, FLAC, MP3, and OGG files and directory trees.
     - Controls: Start Queue, Pause Worker, Refresh, Clear Completed, Clear Failed.
     - Status filtering tabs: All, Queued, Done, Failed.
     - Job row items with real-time percentage progress bars, stage badges (`preparing`, `separating`, `packaging`, `validating`), model/device tags, retry/cancel/remove actions, and expandable error diagnostics.
  2. **LibraryView**:
     - Scans output stem library directory.
     - Displays `.viibstems` package cards with track title, package UUID, audio duration, file size, and stem pills (`vocals`, `drums`, `bass`, `other`, `guitar`, `piano`).
     - Includes integrated "Validate Package" action to check package integrity against the manifest contract.
  3. **SettingsDoctorView**:
     - Stem library directory path configuration.
     - Default model selector (`htdemucs_6s` 6-stem or `htdemucs` 4-stem).
     - Compute device preference (`auto`, `cuda`, `mps`, `cpu`) and GPU-to-CPU fallback toggle.
     - Model weight cache card displaying download state, size, and pre-download button.
     - Full System Doctor diagnostics displaying PyTorch version, CUDA GPU runtime, Apple MPS, FFmpeg/FFprobe availability, and available disk space.

---

## 4. Native Desktop Shell (`desktop/src-tauri/`)

- Configured with Tauri v2 (`tauri.conf.json`, `Cargo.toml`, `src/main.rs`).
- Native window configuration:
  - Width: 1180px, Height: 780px (min width: 850px, min height: 620px).
  - Dark window theme and native decorations.
  - Development URL: `http://127.0.0.1:5173`.
  - Production frontend distribution: `../dist`.

---

## 5. CLI Command Reference

The desktop UI server can be launched directly via the CLI:

```bash
# Launch UI server and open the browser automatically
viib-stemlab ui

# Specify a custom port and disable auto-opening browser
viib-stemlab ui --port 8765 --no-browser

# Bind to all interfaces (e.g., for local network access)
viib-stemlab ui --host 0.0.0.0 --port 9000

# Specify custom stem library and queue database paths
viib-stemlab ui --library "D:\Music\Stems" --db "D:\StemLab\queue.db"
```

---

## 6. Verification & Test Coverage

- **Python UI & CLI Tests** (`tests/test_ui_server.py`, `tests/test_cli.py`):
  - `test_ui_server_lifecycle_and_queue_flow`: Verifies server spin-up, health endpoint, batch track addition, queue status retrieval, background runner starting/stopping, doctor endpoint, models endpoint, and library scanning.
  - `test_ui_server_error_cases`: Verifies error handling for unknown routes (404), empty additions (400), non-existent retry jobs (404), job removal, and corrupt package validation.
  - `test_ui_server_serves_desktop_dist`: Verifies that `StemLabHTTPServer` correctly serves the compiled React `desktop/dist/index.html` file.
  - `test_cli_ui_parser` & `test_cli_ui_run_keyboard_interrupt`: Verifies `viib-stemlab ui` command-line parsing, runner setup, and graceful shutdown on interrupt.
- **Frontend Unit Tests** (`desktop/src/api.test.ts`):
  - Tested with Vitest: API client queue fetching, track addition, system doctor report parsing, and stem library querying (100% pass rate).
- **Total Test Suite**:
  - Python tests: **89/89 passed** (0 warnings, 0 failures).
  - Frontend tests: **4/4 passed** (0 failures).
