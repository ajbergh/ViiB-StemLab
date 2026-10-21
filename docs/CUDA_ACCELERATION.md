# Downloadable Windows CUDA acceleration

The Windows installer retains its CPU backend. A separately downloaded, frozen
CUDA worker runs GPU separation in another process, sharing the existing model
weights. Users need a compatible NVIDIA driver; Python, pip and the CUDA Toolkit
are not required. The application does not install system drivers.

## User experience

On desktop startup, NVIDIA detection runs independently of CPU Torch. With the
default Auto device preference, setup automatically downloads a CUDA worker,
verifies every part and the assembled archive, extracts into a temporary directory,
and executes a GPU kernel before enabling CUDA. CPU processing remains available
during setup. Existing CPU jobs keep running; later Auto jobs select CUDA once ready.

Settings provides progress, cancel, retry, and a persistent automatic-download
checkbox. Selecting CPU prevents automatic downloads. Disabling downloads retains
an installed worker. Cancel disables automatic downloads; Install/Retry still works
manually. The GPU-to-CPU fallback preference covers unavailable CUDA, GPU memory
errors, inference failures and worker crashes. Packages record the actual device
and whether fallback occurred.

The initial worker uses Torch/TorchAudio 2.6.0+cu124 and conservatively requires
Windows NVIDIA driver 551.78 or newer. Unsupported GPU architectures fail the
execution check and remain on CPU. This is not an RTX 50-series runtime; those
GPUs need a separately tested newer Torch/CUDA build. Downloadable workers target
Windows x64; local macOS/Linux acceleration continues using the installed runtime.

## Building and publishing

Run `scripts\build_cuda_worker.bat` to create an isolated CUDA environment, freeze
the worker with decoder binaries and notices, run startup smoke checks, and create
`dist/cuda/windows-cuda.json` and `*.zip.part01`, `*.zip.part02`, etc. `-CheckOnly`
checks prerequisites. Python 3.12/3.13 x64 and internet are required. Node/Rust are
required only for the desktop installer. CPU/CUDA builds use separate environments
and share a build lock.

The manifest records protocol, platform, version, exact archive/part sizes and full
SHA-256 hashes, executable name, and minimum driver. Parts are limited to 1 GiB to
fit [GitHub's per-file limit](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).
The old manifest is removed before rebuilding and the new manifest is written
last, preventing stale manifests after an interrupted build. Publish **the
manifest and all the parts it lists**, together, to the `cuda-worker-v1` release
in `ajbergh/ViiB-StemLab`. Do not mutate a published worker version.

The manual Windows CUDA worker candidate workflow uploads build artifacts without
publishing a release. Hosted Windows runners cannot test GPU execution. Before
publication, validate `stemlab-backend.exe --cuda-probe`, real separation, routing
from the CPU backend, and clean-machine behavior. Apply release signing when
configured. The downloader trusts the HTTPS manifest and verifies its checksums;
independent manifest signatures are not implemented.

The default endpoint is
`https://github.com/ajbergh/ViiB-StemLab/releases/download/cuda-worker-v1/windows-cuda.json`.
Until the assets are published, setup reports unavailable and CPU remains usable.
For controlled testing or alternate hosting, set `VIIB_STEMLAB_CUDA_MANIFEST_URL`
to a trusted HTTPS manifest before launching the app; an empty value disables
remote discovery. End users do not need this override with a published release.

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
