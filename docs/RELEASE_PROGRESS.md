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
