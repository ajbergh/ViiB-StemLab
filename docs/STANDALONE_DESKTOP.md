# Standalone desktop development and distribution

The default installed experience is a Tauri graphical window. Tauri owns an independent Python/Demucs backend and uses native file/folder dialogs. No terminal, Node, Rust, or separately installed Python is needed by an end user. Model weights are downloaded on first use and cached for later offline use.

This branch supplies a Windows CPU installer candidate workflow and a portable runtime build script. Public release readiness still requires clean-machine installer testing, notice review, and signing. macOS/Linux native compilation is checked in CI; their installers and GPU runtimes require separate platform validation.

## Development

Install Python 3.12 or 3.13, Node 22, Rust, the Tauri platform prerequisites, and FFmpeg/FFprobe for compressed audio. From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[demucs,dev,packaging]"
cd desktop
npm ci
npm run tauri dev
```

On macOS/Linux use `.venv/bin/python` and your shell's normal commands. The native development launcher uses the repository's `.venv`; `VIIB_STEMLAB_PYTHON` can explicitly select another interpreter. Tauri starts the backend automatically. For browser-only development, start `viib-stemlab ui --no-browser` and `npm run dev` separately; the browser UI accepts absolute filesystem paths because browsers cannot expose native file paths.

## Build an installer candidate

On Windows, run `scripts\build_windows.bat` from any working directory. It prepares an isolated CPU environment, fetches checksum-pinned decoder tools, checks the backend, and builds an unsigned installer plus SHA-256 file under `dist\windows\`. Run `scripts\build_windows.bat -CheckOnly` to check prerequisites without installing or building, or `scripts\build_windows.bat --help` for usage. Python 3.12/3.13 x64, Node 22+, Rust, Visual Studio C++ build tools, and a Windows SDK are required. Internet access is needed for uncached dependencies. Close running StemLab windows before building.

The batch entry point delegates filesystem operations to `scripts/build_windows.ps1`. It preserves the previous bundled runtime until the replacement passes its startup checks and keeps a backup during installer creation. It does not modify the CUDA development environment. The manual commands below remain available for other platforms and custom decoder distributions.

Use a clean environment for each OS/architecture. Install the desired compatible Torch runtime first, then `.[demucs,packaging]`. The first automated Windows workflow uses Torch 2.6 CPU; this does not provide CUDA acceleration. Source/development environments can still use supported CUDA/MPS runtimes.

Supply standalone FFmpeg and FFprobe binaries for the target platform and the exact decoder distribution's notices, source/build information, and license texts. Avoid dynamically linked decoder binaries unless all required libraries are included and checked on the target platform.

```powershell
python packaging/build_backend.py --ffmpeg-dir C:/decoder/bin --ffmpeg-notices C:/decoder/NOTICES.txt
python packaging/smoke_backend.py desktop/src-tauri/runtime/stemlab-backend.exe --require-runtime
# Downloads weights and validates a real short CPU separation:
python packaging/smoke_backend.py desktop/src-tauri/runtime/stemlab-backend.exe --require-runtime --separate
cd desktop
npm ci
npm run package -- --bundles nsis
```

Use the executable name without `.exe` on macOS/Linux. Keep the entire generated `runtime` directory, including `_internal` and notices. The build script deliberately refuses to overwrite an existing runtime: inspect and remove that generated directory before rebuilding. `npm run package` supplies `tauri.release.conf.json`, which embeds it as a resource. Plain frontend builds do not bundle Python. The Windows release configuration includes the offline WebView2 installer.

The **Windows standalone candidate** GitHub workflow prepares pinned decoder binaries, verifies their checksum, builds the runtime, tests startup/authentication/shutdown and the internal Demucs worker, optionally performs real separation, generates dependency inventories, and uploads an unsigned NSIS candidate. It does not publish a release. Run it from this branch after pushing the branch.

## Runtime behavior

- Backend binds `127.0.0.1` on an available port, never a fixed public interface.
- A per-launch secret is returned only over the owned process pipe and Tauri's local command bridge. Every API request in desktop mode requires it.
- One native instance is allowed per user. Reopening focuses the existing window.
- The launcher waits for the backend handshake; the UI checks health before loading preferences. Startup failures and later connection loss are visible.
- Closing the app cancels active processing, waits for cleanup, and preserves queued jobs. The next launch recovers interrupted jobs. A disconnected launcher pipe also requests backend shutdown.
- Settings, queue state, logs, and cached weights live outside the installation directory. Native app data uses Tauri's `app_local_data_dir()` under `com.viib.stemlab`; an absolute `VIIB_STEMLAB_HOME` explicitly overrides that location. `desktop.log` and `backend-stderr.log` record failures. CLI state remains at its existing location; native state is separate by default.
- The supported GUI model is `htdemucs_6s`. The package contract still requires six aligned stems.
- New downloads are validated against their length and known SHA-256 prefix before promotion. Previously cached model files retain the existing cache behavior.

## Release checks

Verify install, launch, native picker/drag/drop, first-run download/retry, MP3/OGG decoding, cancellation, restart, offline reuse, library validation, and uninstall on clean target systems. Test CUDA/MPS separately on real hardware. Review Python/native/frontend license inventories and decoder redistribution requirements before publishing. Signing, notarization, updates, and MediaHub conformance remain separate release work.

Implementation goals and ongoing evidence: [STANDALONE_GOALS.md](STANDALONE_GOALS.md), [STANDALONE_PROGRESS.md](STANDALONE_PROGRESS.md).

References: [Tauri resource bundling](https://v2.tauri.app/develop/resources/), [Tauri dialogs](https://v2.tauri.app/plugin/dialog/), [PyInstaller frozen-process guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html), and [decoder build provenance](https://www.gyan.dev/ffmpeg/builds/).
