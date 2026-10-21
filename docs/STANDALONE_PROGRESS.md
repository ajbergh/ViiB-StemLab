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
- [x] Automated checks and final review

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

## 2026-10-21 — Installer candidate completed

- `npm run package -- --bundles nsis` completed successfully (exit 0).
- Artifact: `desktop/src-tauri/target/release/bundle/nsis/ViiB StemLab_0.1.0_x64-setup.exe`.
- Size: 425,288,944 bytes (approximately 406 MiB). CPU runtime, decoder binaries, notices/inventories, and offline WebView2 installer are included; model weights download through the GUI on first use.
- SHA-256: `80810b31d0ec5d8288a000dc0d686749b446cfc671c3938591f8bc4a023da9b8`.
- Signature status: `NotSigned`; this is an internal candidate, not a signed public release.
- Final library duration display verified as `0:03` for the three-second synthetic track. Saved native UI evidence shows `Valid ViiB Package` after graphical validation.
- Production frontend dependency audit: zero vulnerabilities. The full audit also reported advisories in existing development tools; those toolchain migrations remain separate work.
- Implementation commit: `a549642`. Goal/progress/build documents are versioned on `feat/standalone-desktop`; generated runtime binaries and screenshots are intentionally ignored by Git.

## 2026-10-21 — Windows batch build entry point

- Added `scripts/build_windows.bat` and its PowerShell implementation for an end-to-end CPU installer build.
- Added prerequisite/help modes, pinned decoder download verification, backend startup checks, dependency inventories, safe runtime staging, and installer/checksum collection under `dist/windows/`.
- Kept the packaging environment separate from CUDA development. Generated-directory operations are limited to explicit workspace paths; concurrent builds are blocked by a build lock.
- Verified the batch help and prerequisite-only paths through Windows PowerShell. The underlying runtime and installer commands were verified by the standalone work above; this follow-up does not require rebuilding the unchanged application.

## 2026-10-21 — Build checksum compatibility fix

- Replaced all three `Get-FileHash` calls in the Windows build helper with streaming .NET SHA-256 hashing, removing the unavailable cmdlet dependency.
- Prerequisite-only mode now exercises checksum support. A complete, verified `.download` left by a failed build is reused on retry; incomplete or invalid downloads are fetched again.
- Verified empty-file and `abc` SHA-256 vectors, literal paths containing spaces/brackets, and file-handle disposal in Windows PowerShell with `Get-FileHash` deliberately blocked. `scripts/build_windows.bat -CheckOnly` passed. The full installer pipeline was not rerun for this fix.

## External validation still required

- Downloadable CUDA acceleration is implemented and verified with a real frozen CPU parent and RTX 4060 Ti worker, including HTTPS multipart setup, CUDA separation and offline restart. See [CUDA progress](CUDA_PROGRESS.md) and [build/publication instructions](CUDA_ACCELERATION.md). Publishing its release assets and rebuilding the desktop installer remain necessary before distribution.

- Install and process audio on clean Windows, Apple Silicon macOS, and Linux systems.
- Perform hands-on native file-picker and operating-system drag/drop QA; the native event-to-queue path was exercised programmatically.
- Verify CUDA and MPS on physical hardware.
- Configure signing/notarization credentials before public distribution.
- Review redistribution notices and existing development-tool advisories before publishing.
