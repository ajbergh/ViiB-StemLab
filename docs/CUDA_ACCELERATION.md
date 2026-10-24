# Downloadable Windows CUDA acceleration

The Windows installer retains its CPU backend. A separately downloaded, frozen
CUDA worker runs GPU separation in another process, sharing the existing model
weights. Users need a compatible NVIDIA driver; Python, pip and the CUDA Toolkit
are not required. The application does not install system drivers.

## User experience

On desktop startup, NVIDIA detection runs independently of CPU Torch. With the
default Auto device preference, setup automatically downloads a CUDA worker,
verifies every part and the assembled archive, extracts into a temporary directory,
and checks both a GPU kernel and model-checkpoint import compatibility before enabling CUDA. CPU processing remains available
during setup. Existing CPU jobs keep running; later Auto jobs select CUDA once ready.

Settings provides progress, cancel, retry, and a persistent automatic-download
checkbox. Selecting CPU prevents automatic downloads. Disabling downloads retains
a compatible installed worker. Outdated worker versions are rejected and replaced during the next enabled setup. Cancel disables automatic downloads; Install/Retry still works
manually. The GPU-to-CPU fallback preference covers unavailable CUDA, GPU memory
errors, inference failures and worker crashes. Packages record the actual device
and whether fallback occurred.

The current catalog supports modern Torch 2.7.1 + CUDA 12.8 and legacy
Torch 2.6.0 + CUDA 12.4. See [GPU profiles](GPU_PLATFORMS.md) for driver
and architecture requirements. Downloadable workers target Windows x64; local
macOS/Linux acceleration continues using the installed runtime.

## Building and publishing

Run `scripts\build_cuda_worker.bat` to create an isolated CUDA environment, freeze
the worker with decoder binaries and notices, run startup smoke checks, and create
`dist/cuda-modern/windows-cuda.json` (modern) or `dist/cuda/windows-cuda.json` (legacy) and `*.zip.part01`, `*.zip.part02`, etc. `-CheckOnly`
checks prerequisites. Python 3.12/3.13 x64 and internet are required. Node/Rust are
required only for the desktop installer. CPU/CUDA builds use separate environments
and share a build lock.

The manifest records protocol, platform, version, exact archive/part sizes and full
SHA-256 hashes, executable name, and minimum driver. Parts are limited to 1 GiB to
fit [GitHub's per-file limit](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).
The old manifest is removed before rebuilding and the new manifest is written
last, preventing stale manifests after an interrupted build. Publish **the
manifest and all the parts it lists**, together, to the release selected by
`cuda_profiles.py`: `cuda-worker-v5` for modern and `cuda-worker-v6` for legacy.
These are new Demucs 4.1.0/safetensors runtime identities; publish them before
distributing the updated installer. Do not mutate a published worker version.

The manual Windows CUDA worker candidate workflow uploads build artifacts without
publishing a release. Hosted Windows runners cannot test GPU execution. Before
publication, validate `stemlab-backend.exe --cuda-probe`, real separation, routing
from the CPU backend, and clean-machine behavior. Apply release signing when
configured. The downloader trusts the HTTPS manifest and verifies its checksums;
independent manifest signatures are not implemented.

Automatic setup selects the matching immutable release endpoint from
`cuda_profiles.py`. A Full installer includes the CPU engine; its CUDA worker
still comes from this separate release and per-user cache.
Until the assets are published, setup reports unavailable and CPU remains usable.
For controlled testing or alternate hosting, set `VIIB_STEMLAB_CUDA_MANIFEST_URL`
to a trusted HTTPS manifest before launching the app; an empty value disables
remote discovery. End users do not need this override with a published release.

## Testing a local build before publishing

A Full installer includes the CPU engine. CUDA remains a separate runtime, so a
local installer still gets HTTP 404 until its matching CUDA release is published.
You can install your own CUDA package locally without hosting it:

```bat
scripts\build_cuda_worker.bat -CudaProfile modern
build\cuda-modern-packaging-venv\Scripts\python.exe -m viib_stemlab cuda import-local dist\cuda-modern\windows-cuda.json --app-data "%LOCALAPPDATA%\com.viib.stemlab"
```

The JSON manifest and all listed archive parts must be in the same directory.
For the legacy profile, use `-CudaProfile legacy`, `build\cuda-packaging-venv\Scripts\python.exe`, and `dist\cuda\windows-cuda.json`.
If you use `VIIB_STEMLAB_HOME`, pass that app-data path instead. Fully exit and
reopen StemLab after import. This does not require another installer build.

If an uninstall or app-data cleanup removes `runtimes/current.json` and the worker
directory, run the local import again after reinstalling. The Full installer does
not restore CUDA. Reuse your existing compatible manifest and archive parts;
rebuilding the worker is unnecessary. Restart StemLab after restoring it.

Local import performs the normal archive hash, extraction, GPU, model-runtime,
and receipt checks. It requires a current compatible profile and activates a new
generation only after verification. Existing runtimes, model weights, libraries,
and queue state are preserved. Public downloads still require HTTPS. Publishing
the runtime release is required for automatic setup on other machines.

## Storage and lifecycle

Workers live in the per-user app-data `runtimes/` directory. An atomic `current.json`
receipt inventories every extracted file. Each desktop launch hashes the installed
files and checks GPU execution before enabling CUDA. Verified installations work
offline. Traversal, symlinks/junctions, duplicate paths, wrong sizes/checksums,
incompatible protocols, and insufficient disk space prevent activation.

Version directories are never overwritten while potentially in use. Retired
versions can be removed manually with the app closed. Failed/cancelled staging
downloads are removed; retry restarts the download. Windows DLL search isolation
and a fresh PyInstaller environment keep CPU and CUDA Torch libraries separate.
Probes and separation own their subprocess lifetimes; cancellation stops them.
The existing `TORCH_HOME` model cache is shared.
