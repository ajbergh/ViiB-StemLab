# ViiB StemLab 0.2.0 release goals and progress

- [x] Merge green GPU/macOS PR #7.
- [x] Build Windows Full/On-demand installers and validate packaged CPU processing and native setup.
- [x] Verify modern CUDA kernel and six-stem processing from merged source on RTX 4060 Ti.
- [x] Verify experimental macOS Full/On-demand DMGs, runtime inventory and CPU/MPS processing.
- [x] Independently verify final Windows downloads and installer contents.
- [x] Publish all immutable runtime payloads and verify anonymous URLs.
- [x] Validate final Windows CPU app using the public modern CUDA worker and cached restart.
- [x] Publish v0.2.0 and verify uploaded release assets.

Release source: `7d8550d51eac65f1bf541680b2bab772ce0ce076` (merged PR #7).
The macOS candidate source tree at `6eddfe5` is identical to that merged tree.
Existing v0.1.0 and legacy CUDA worker v1 assets remain unchanged.

## Evidence

- [Windows packaging](https://github.com/ajbergh/ViiB-StemLab/actions/runs/39719581688):
  Full/On-demand installers, frozen CPU MP3 separation and native Full offline /
  HTTPS On-demand setup, cached reuse, repair and checksum rejection passed.
- [macOS packaging](https://github.com/ajbergh/ViiB-StemLab/actions/runs/39718385460):
  mounted final DMG signatures, flavor and exact runtime inventory passed. Native
  setup/repair, frozen CPU FLAC, a real MPS kernel and forced six-stem MPS processing
  with CPU fallback disabled passed. Output packages validated and recorded MPS.
- Modern Torch 2.7.1/CUDA 12.8 worker from merged main passed real six-stem CUDA
  processing with CPU fallback disabled. Four archive-part hashes and the assembled
  archive hash passed independent verification. Uploaded CUDA runtime and macOS
  runtime sizes/digests match; all their URLs returned anonymous HTTP 200.
- Source/desktop CI passed on Windows, Linux and macOS. Local implementation
  validation included 155 Python tests, frontend tests/build and native checks.
- Final Windows installer checksums match. Isolated extraction verified Full's
  exact runtime inventory and the On-demand flavor's embedded public manifest URL
  and absence of the bundled runtime. Uploaded app/runtime sizes and digests match.
- Public CPU, modern CUDA and experimental macOS runtime releases are published;
  manifests and all archives/parts returned HTTP 200 without authentication.
- The final Full installer's frozen CPU app automatically selected/downloaded the
  default public modern CUDA worker, verified/extracted/probed it, completed and
  validated a real Auto six-stem CUDA job with CPU fallback disabled, and reused
  it after restart with downloads disabled and an unreachable manifest override.
- [v0.2.0](https://github.com/ajbergh/ViiB-StemLab/releases/tag/v0.2.0) is public
  with Windows Full/On-demand and experimental Mac Full/On-demand downloads.
  All 12 application asset sizes/digests match; every application/runtime asset
  URL returned anonymous HTTP 200. The release includes provenance/hash reports.

## Release limits

- macOS ARM64 builds are experimental, ad-hoc signed and not Developer ID notarized.
  Gatekeeper may block opening them; Intel Macs are not included.
- Windows installers are unsigned. Clean-machine install/upgrade/uninstall,
  broader Mac hardware, long-track and low-memory testing remain unverified.
- RTX 20/30/50 are runtime targets but have not been physically tested.
- Hosted MPS processing passed; Metal models can execute some operations on CPU
  internally. CPU fallback was disabled for the forced-MPS validation job.
