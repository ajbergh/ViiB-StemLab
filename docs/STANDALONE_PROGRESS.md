# Standalone desktop progress

## 2026-10-21 — Started

- Created branch `feat/standalone-desktop` from the existing clean checkout.
- Recorded architecture and acceptance criteria in `STANDALONE_GOALS.md`.
- Confirmed the existing core and React UI can be retained.
- Confirmed frozen Demucs needs an explicit worker entry point; the development `python -m` command cannot be used inside a frozen executable.

## Work status

- [x] Packaged backend lifecycle and private API
- [x] Persistent backend preferences
- [x] Model setup progress and retry
- [x] Tauri backend orchestration and startup error UI
- [x] Native file/folder selection and drag/drop
- [x] Runtime/decoder bundling and third-party notice inventory
- [x] Desktop CI definitions and packaged startup smoke
- [ ] Automated checks and final review

## 2026-10-21 — Integration implemented

- Added dynamic loopback startup handshake, per-launch bearer authentication, restricted origins, and launcher-owned shutdown.
- Added frozen-worker dispatch for Demucs, stable app-data preferences, and model download status/error/retry reporting.
- Connected Tauri v2 dialogs and native drag/drop; browser mode explicitly accepts absolute paths.
- Added startup/reconnection diagnostics and first-run model setup; removed remote font loading and the incompatible four-stem model option.
- Generated desktop icons from the versioned SVG source.
- Added PyInstaller runtime preparation, packaged-backend smoke checks, cross-platform desktop compilation CI, and a manually triggered Windows CPU installer candidate workflow.
- Validation so far: 110 Python tests passed; Ruff passed; frontend build passed; native `cargo check` passed. Frozen runtime build is in progress.

## 2026-10-21 — Frozen-runtime diagnosis

- The first bundled runtime completed its handshake and API authentication/settings checks, but the doctor endpoint hung during deferred Torch import in an HTTP request thread.
- Focused frozen-worker/probe experiments ruled out generic missing DLLs and slow CUDA detection. Stack evidence located the stall in native NumPy/OpenBLAS library loading.
- Moved initial Torch/native-library loading to the backend main thread before readiness. Rebuilding and re-running packaged startup/separation checks.
- The rebuilt backend passed diagnostics and independent frozen-worker startup. Added an explicit PyInstaller environment reset for independent workers; the remaining queue-worker hang was subsequently traced to inherited stdin, as recorded below.
- Browser checks confirmed output/device preferences survive reload; settings render without browser console errors.
- Native WebView verification passed startup, private API connection, first-run model download, diagnostics, a synthetic native drop event with a real fixture path, and queued-job cancellation/removal. No native WebView console errors were reported.
- Worker stack inspection identified a second Windows issue: inherited launcher stdin blocked child Python stdio initialization. Worker stdin is now disconnected with `DEVNULL`; the launcher lifetime pipe remains owned by the backend.
- Local CUDA runtime exceeded NSIS's size limit. The installer candidate uses a separate CPU-only packaging environment, matching the CI workflow.

## 2026-10-21 — CPU runtime verified

- Isolated CPU source runtime generated and validated a real six-stem WAV package.
- Final frozen CPU runtime passed readiness, authentication rejection, persistent preferences, Torch/Demucs/decoder diagnostics, independent worker launch, real MP3 decoding/separation, package validation, and EOF shutdown.
- Full Python suite: 112 passed. Final focused backend regression checks: 21 passed. Frontend: 5 tests passed and production build passed. Rust compilation and formatting passed.
- Native review window and its backend closed cleanly. Browser and WebView screenshots are under ignored `output/playwright/`.
- Building the final unsigned CPU installer candidate. Hosted CI workflows have been added but have not been run remotely in this session.
- Final native-window workflow passed with Python and system decoder tools absent from PATH: load cached weights, queue a synthetic track through a native event, start processing in the GUI, complete six-stem generation, browse the library, and validate the resulting package. No WebView console errors.
- Fixed a library duration field mismatch exposed by that workflow (`duration` in the v1 manifest). Selected zlib installer compression to keep candidate builds practical for the large bundled runtime.

## External validation still required

- Install and process audio on clean Windows, Apple Silicon macOS, and Linux systems.
- Verify CUDA and MPS on physical hardware.
- Configure signing/notarization credentials before public distribution.
