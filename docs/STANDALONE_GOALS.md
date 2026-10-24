# Standalone desktop goals

Branch: `feat/standalone-desktop`

## Product acceptance criteria

- Installing and opening StemLab launches a graphical window without a terminal or separately installed Python.
- Tauri owns a bundled backend, waits for readiness, reports startup errors, and shuts processing down safely.
- Native file/folder dialogs and desktop drag/drop submit real filesystem paths.
- Output folder, model, device, and CPU fallback preferences survive restart.
- First-run model setup shows progress, errors, and retry; cached models support offline processing.
- The UI offers only models supported by the four-stem package contract.
- Desktop builds include the runtime, audio decoder tools, icons, and third-party notices.
- CI checks Python, frontend, native compilation, and packaged-backend startup.

## Architecture

Keep React + Tauri and Python/Demucs. Ship a PyInstaller directory bundle as a Tauri resource. The backend binds a dynamic loopback port and generates a per-launch API secret. A Tauri command delivers connection information to the local frontend. Stdin ownership provides orderly shutdown and detects launcher exit. The frozen executable has an explicit internal Demucs worker mode.

## Delivery and verification

1. Backend lifecycle, authentication, packaged paths, settings, and model-download state.
2. Native launcher, connection UX, dialogs, drag/drop, first-run setup.
3. Runtime bundling, decoder inclusion, icons, notices, and CI.
4. Relevant automated tests and local build/smoke checks.

Clean-machine installer tests and real CUDA/MPS hardware validation must be recorded separately from source/build checks. Do not claim cross-platform release readiness from a single development machine. Model downloads require internet once; fully offline installation requires pre-provisioned weights. Signing and publication require release credentials.
