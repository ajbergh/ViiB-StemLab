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
