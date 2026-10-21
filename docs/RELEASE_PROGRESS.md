# Windows 0.1.0 release progress

## Preparation

- User authorized PR creation, merge, builds and public release publication.
- Starting source: `8fd618e` on `feat/standalone-desktop`; working tree clean.
- Local checks passed: 145 Python tests, Ruff, lock validation, 5 frontend tests,
  production frontend build, Rust formatting and 5 native tests. The native
  payload integration test requires an explicit payload/HTTPS fixture invocation.
- CPU and CUDA default release endpoints currently return 404. Existing locally
  hosted validation is insufficient to establish public download availability.
- GitHub authentication works outside the restricted process sandbox. Repository
  is public; no prior release or existing PR for this branch was found.

## PR and packaged GPU validation

- Opened PR #5: https://github.com/ajbergh/ViiB-StemLab/pull/5 .
- Full installer CPU backend downloaded/verified the real CUDA worker from a
  local HTTPS fixture. Real six-stem Auto separation passed with fallback disabled,
  package validation succeeded with `actual_device=cuda`, and offline restart
  reverified files and executed the GPU probe successfully.
- Initial hosted CI exposed a 20-second startup test timeout on a cold macOS
  runner. Aligned that subprocess integration test with the launcher's existing
  60-second startup budget and added timeout diagnostic output. Product startup
  behavior is unchanged; hosted checks will be rerun before merge.

## Merged source and rebuilt CPU release

- All nine PR checks passed. PR #5 merged as
  `42224f93f96cff64b1d26d9b603dc82c42f13f25`; merged-main Python and desktop
  workflows also passed on Linux, Windows and macOS.
- Rebuilt both installers and CPU payload from the merged source. Full is
  488,400,750 bytes; On-demand is 2,462,388 bytes. Independently verified installer
  checksums before uploading to an unpublished application draft.
- Rebuilt native Full/offline and HTTPS On-demand integration passed in 85.81
  seconds: download/probe, offline reuse, repair and bad-checksum rejection.
- Published https://github.com/ajbergh/ViiB-StemLab/releases/tag/cpu-runtime-0.1.0
  after comparing uploaded asset sizes/SHA-256 digests against local files.
  Anonymous requests to the default manifest and archive returned HTTP 200.
- Extracted both final NSIS installers for native UI checks, without changing the
  machine's registered installation. Isolated QA state and a PATH containing only
  Windows system directories ensured no developer Python/Node was required.
- Full started with unreachable processing download endpoints and completed real
  CPU separation with a validated package. On-demand downloaded from the default
  public GitHub URL, reached the app, and completed real CPU separation with a
  validated package. On-demand browser console: zero errors/warnings.
- Rebuilt CUDA worker passed a real kernel and six-stem forced-CUDA separation on
  RTX 4060 Ti, using the model fetched through public On-demand setup. CUDA archive
  compression completed; all per-part and assembled SHA-256/size checks passed.
  Published https://github.com/ajbergh/ViiB-StemLab/releases/tag/cuda-worker-v1
  after uploaded SHA-256/size verification. Anonymous requests to the manifest
  and every part returned HTTP 200 with correct sizes. The native On-demand app
  automatically downloaded all parts from the default public URL, verified and
  activated the worker, and completed Auto separation with fallback disabled.
- Full then used the same shared application data with remote CUDA discovery
  disabled and an unreachable CPU manifest. Installed-file verification and the
  GPU probe passed; another real Auto job completed on CUDA with fallback disabled.
  Both GPU packages validated. Their manifests recorded `model.device=cuda` while
  the parent reported Torch `2.6.0+cpu` and `autoDevice=cuda`.
- Inspected final native UI screenshots; refreshed Doctor reports CUDA ready,
  available devices `cpu, cuda`, and Auto `cuda`. Browser console: zero errors
  or warnings. QA applications were closed cleanly afterward.

## Published application release

- [ViiB StemLab 0.1.0](https://github.com/ajbergh/ViiB-StemLab/releases/tag/v0.1.0)
  is the latest public application release. It includes both installers, matching
  checksum files, and `release-verification.json` / `release-verification.md`.
- All six uploaded application asset sizes/SHA-256 digests matched local files
  before publication. Anonymous installer HEAD requests returned HTTP 200 and
  correct sizes; downloaded checksum files and verification reports matched local
  copies. Checksum entries match the public filenames.
- Source CI passed on Windows/Linux/macOS; the published binaries are Windows x64.
  Native QA used extracted NSIS contents on this machine, not a clean OS install.
  Installers remain unsigned. Broader GPU/driver and install/upgrade/uninstall
  coverage is not claimed; the initial CUDA worker does not support RTX 50-series.

## Application installer checksums

Published asset names use hyphens because GitHub normalizes spaces in asset names.
Checksum file entries match the actual published download filenames.

| Installer | SHA-256 |
| --- | --- |
| `ViiB-StemLab_0.1.0_x64-full-setup.exe` | `6539607a49942c736fd2c684b71c68a4ec1ee960f399076277721f61c9c33e36` |
| `ViiB-StemLab_0.1.0_x64-ondemand-setup.exe` | `11f983c87324a826e26590e7468cf259c421dba2eb034dce58feecf51c168724` |
