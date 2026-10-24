# 0.3.0 release publication

## Downloads and runtime dependencies

[ViiB StemLab 0.3.0](https://github.com/ajbergh/ViiB-StemLab/releases/tag/v0.3.0)
contains Windows x64 EXE, experimental Apple Silicon/macOS 14+ DMG and
experimental Linux x64 Debian installers, each in Full and On-demand variants.
Every installer has an adjacent SHA-256 file. The release also includes merged
source, decoder notices/source and detailed verification reports.

The matching runtime manifests and all archives/parts are published together:

| Target | Release |
| --- | --- |
| Windows CPU | [cpu-runtime-0.3.0](https://github.com/ajbergh/ViiB-StemLab/releases/tag/cpu-runtime-0.3.0) |
| Apple Silicon CPU/MPS | [macos-runtime-0.3.0](https://github.com/ajbergh/ViiB-StemLab/releases/tag/macos-runtime-0.3.0) |
| Linux x64 CPU | [linux-runtime-0.3.0](https://github.com/ajbergh/ViiB-StemLab/releases/tag/linux-runtime-0.3.0) |
| Modern Windows CUDA: Torch 2.7.1 / CUDA 12.8 | [cuda-worker-v5](https://github.com/ajbergh/ViiB-StemLab/releases/tag/cuda-worker-v5) |
| Legacy Windows CUDA: Torch 2.6.0 / CUDA 12.4 | [cuda-worker-v6](https://github.com/ajbergh/ViiB-StemLab/releases/tag/cuda-worker-v6) |

Runtime publication precedes application publication. Uploaded sizes and GitHub
asset digests match verified local files; anonymous public download probes and
public JSON manifest digest checks pass. Older published releases are unchanged.

## Source and build evidence

PR [#10](https://github.com/ajbergh/ViiB-StemLab/pull/10) was squash merged as
`2677542c54d8f9305b1b6f4c07bf32b5713ba1ac` after six cross-platform CI checks passed.
Windows/macOS/CUDA artifacts use that source. Linux packaging PR
[#11](https://github.com/ajbergh/ViiB-StemLab/pull/11) was squash merged as
`a3d80446cf10004f8d4b530db607efed37059f52`; its build source `e4e34f9` has the same
Git tree as merged main (`691878d23d72dba87cc4eef224ef2ec70af90421`).
The published source ZIP uses merged main. Source versions are synchronized at 0.3.0.

| Build | Evidence |
| --- | --- |
| Windows Full/On-demand and CPU payload | [40106288671](https://github.com/ajbergh/ViiB-StemLab/actions/runs/40106288671) |
| Apple Silicon Full/On-demand and CPU/MPS payload | [40106290275](https://github.com/ajbergh/ViiB-StemLab/actions/runs/40106290275) |
| CUDA modern | [40106292023](https://github.com/ajbergh/ViiB-StemLab/actions/runs/40106292023) |
| CUDA legacy | [40106293912](https://github.com/ajbergh/ViiB-StemLab/actions/runs/40106293912) |
| Linux Full/On-demand and CPU payload | [40107996686](https://github.com/ajbergh/ViiB-StemLab/actions/runs/40107996686) |

All five build workflows passed. Downloaded Actions artifact digests, six
installer sidecars, the source archive and all three runtime ZIP inventories
verify. Engine inventories contain Demucs 4.1.0 and pinned Torch versions;
macOS/Linux runtime ZIPs preserve executable permissions.

Windows passed packaged CPU MP3 separation and native Full offline/HTTPS
On-demand setup, cached reuse, repair and checksum rejection. Apple Silicon
passed finished-DMG inventory/signature checks, CPU FLAC processing, native
setup, a real Metal kernel and forced four-stem MPS separation without CPU fallback.
Linux passed the same native setup checks and real CPU FLAC separation against
resources extracted from the finished Full Debian package.

Both downloaded CUDA profiles passed verified local import, actual GPU execution
and four-stem MP3 processing with CPU fallback disabled on RTX 4060 Ti,
driver 610.88. This does not establish other GPU/driver coverage.

Local source checks passed Ruff, 220 Python tests, frontend/native checks and
production frontend build. Merged-main Python and desktop CI passed on all
three operating systems. One Windows CI run hit a timing flake in the existing
file-lock cleanup test: its timer released the lock before PowerShell attempted
cleanup. Only the failed job was rerun and passed.

The initial Linux HTTPS fixture used a CA certificate as its server certificate.
The correction uses a separate CA and signed non-CA leaf; real Windows and Linux
native integration tests passed with that fixture. TLS validation remains enabled.

## Platform and distribution limits

- Windows installers are unsigned. Modern NVIDIA driver policy is 572.61+;
  compatible legacy GPUs require 551.78+. RTX 20/30/50 hardware was not tested.
- macOS builds are experimental and ad-hoc signed, without Developer ID
  notarization. Gatekeeper may block opening them. Intel Mac is not included.
- Linux builds are experimental x64 Debian packages using an Ubuntu 22.04
  baseline and CPU processing. ARM64, RPM/AppImage, broader distribution and
  graphics-driver coverage are not included.
- Clean-machine GUI install/upgrade/uninstall and broad hardware/long-track
  validation remain unverified. Automated backend/setup checks do not establish
  that broader coverage.
