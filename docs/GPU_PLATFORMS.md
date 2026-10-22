# NVIDIA generations and Apple Silicon candidates

This is 0.2.0 candidate work. The published 0.1.0 runtime assets are immutable.
Build success and advertised wheel architectures do not establish physical GPU
coverage. See [goals](GPU_PLATFORM_GOALS.md) and [evidence](GPU_PLATFORM_PROGRESS.md).

## NVIDIA runtime selection

The embedded catalog in `cuda_profiles.py` prefers the modern worker when
`nvidia-smi` reports a matching compute capability and a sufficiently new driver.
Every installed worker still executes an actual CUDA kernel before activation.

| Profile | Runtime | Target capabilities | Windows driver policy | Release |
| --- | --- | --- | --- | --- |
| Modern | Torch/Torchaudio 2.7.1 + CUDA 12.8 | 7.5, 8.0, 8.6, 8.9, 9.0, 10.0, 12.0 | 572.61+ | `cuda-worker-v2` |
| Legacy | Torch/Torchaudio 2.6.0 + CUDA 12.4 | 7.5, 8.0, 8.6, 8.9, 9.0 | 551.78+ | Existing `cuda-worker-v1` |

These targets include GeForce RTX 20/30/40/50 families. Unknown architectures are
not guessed from marketing names. An older `nvidia-smi` without compute-capability
reporting can attempt only the legacy profile, with the kernel probe as a guard.
When the modern manifest is missing (404), compatible older cards may use legacy;
Blackwell must never be routed to legacy. Existing verified cached workers remain
usable offline. Hardware/driver detection does not require CUDA-enabled parent Torch.

The driver policy follows the [CUDA 12.8 Update 1 driver table](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-toolkit-release-notes/index.html).
Blackwell support was introduced in [PyTorch 2.7 / CUDA 12.8](https://pytorch.org/blog/pytorch-2-7/).

```bat
scripts\build_cuda_worker.bat -CudaProfile modern
scripts\build_cuda_worker.bat -CudaProfile legacy
```

Modern uses `build/cuda-modern-packaging-venv`, stages in
`build/windows-cuda-modern-next`, and writes `dist/cuda-modern/`. Legacy keeps its
existing separate paths. CPU Torch is unchanged. The two project extras `demucs`
and `demucs-modern` are mutually exclusive; do not install them into one environment.
The packager checks pinned wheel versions, compiled GPU targets, archive parts,
sizes and hashes. Publish the manifest and every listed part together only after
physical separation tests. An operator HTTPS manifest override remains supported.

## Apple Silicon Full and On-demand builds

Initial target: native ARM64 Apple Silicon, macOS 14+. Intel Mac installers are
not included. CPU and Metal/MPS use the same pinned Torch 2.6 runtime and model.
No separate Metal driver or CUDA package is downloaded. Auto chooses MPS only
after device availability and a real Metal kernel succeed. Demucs may execute
complex-number operations on CPU internally, so GPU acceleration is not a promise
that all operations execute on the GPU.

On a native ARM64 Mac with Python 3.12/3.13, Node 22+, Rust and Xcode command-line tools:

```sh
bash scripts/build_macos.sh --check-only
bash scripts/build_macos.sh                  # both DMGs
bash scripts/build_macos.sh --installer full
bash scripts/build_macos.sh --installer ondemand
```

The build compiles minimal FFmpeg/FFprobe from a checksum-pinned official source
archive. It rejects non-system decoder dynamic dependencies, avoiding a runtime
Homebrew requirement. Configure flags, decoder license and source archive are
provided alongside candidates. For prebuilt standalone decoders, pass
`--ffmpeg-dir /absolute/directory` containing both binaries and `DECODER_NOTICES.txt`.

Outputs: `dist/macos/*-full.dmg`, `*-ondemand.dmg`, matching checksums, and
`dist/macos-components/macos-arm64.json` plus its archive. Full includes runtime,
decoders and weights. On-demand verifies/downloads the same payload under per-user
application data. ZIP extraction preserves executable permissions and rejects links.
Model weights and installed-file hashes are verified before activation.

Candidate workflows do not publish the 0.2.0 runtime endpoint. Use Full for offline
candidate testing; On-demand needs a trusted HTTPS manifest override or publication
of its matching runtime assets. CI exercises the complete download path through a
temporary trusted HTTPS fixture without adding certificates to the OS trust store.

### Signing and notarization

Without credentials, outputs are test candidates (ad-hoc signatures are not a
Developer ID identity). For public distribution configure `APPLE_SIGNING_IDENTITY`
for PyInstaller and Tauri and Tauri's Apple notarization credentials in the build
environment. For the independently downloaded runtime ZIP, set
`STEMLAB_NOTARY_PROFILE` to an existing `notarytool` keychain profile. The runtime is
signed before its inventory/archive hashes are generated. Notarization is submitted
without modifying the signed payload afterwards. Do not commit certificates or secrets.

The hosted Apple Silicon workflow builds candidates and tests actual frozen CPU
separation and native Full/HTTPS On-demand setup. If usable MPS is exposed it also
tests MPS separation; otherwise it explicitly reports the missing GPU validation.
The manual physical workflow requires a trusted self-hosted Mac runner labeled
`self-hosted`, `macOS`, `ARM64`, `stemlab-mps` and forces MPS with CPU fallback disabled.

```sh
desktop/src-tauri/runtime/stemlab-backend --mps-probe
build/macos-packaging-venv/bin/python packaging/smoke_backend.py \
  desktop/src-tauri/runtime/stemlab-backend --require-runtime --separate --device mps
```

Before release, validate actual packages, long tracks, cancellation, low memory,
Full offline startup, On-demand repair/reuse, and signed/notarized clean-machine
installation. Report CPU fallback honestly; do not label a CPU job as verified MPS.
