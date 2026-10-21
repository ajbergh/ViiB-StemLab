# CUDA acceleration progress

## Implementation

- Confirmed the Windows installer intentionally embeds CPU Torch. Model weights are shared between CPU and CUDA.
- Added NVIDIA driver/hardware detection independent of CPU Torch, automatic per-user worker setup, progress, cancel, retry and persistent download preference.
- Added exact SHA-256/size verification for multipart archives, safe extraction, atomic installed receipts, installed-file checks, and actual GPU execution before activation. Windows DLL search isolation separates CPU and CUDA libraries.
- Auto selects the installed worker, shares cached model weights, preserves job cancellation, and records CUDA/CPU fallback provenance. Explicit unavailable CUDA can fall back according to the existing preference.
- Added `scripts/build_cuda_worker.bat`, separate CUDA packaging environment, manual candidate workflow, multipart release generation, and [operator documentation](CUDA_ACCELERATION.md).

## Local validation — 2026-10-21

- Final full Python suite: 136 passed. Tests used the non-hidden workspace directory `build/cuda-final-tests` (the existing discovery rules intentionally skip hidden ancestor directories).
- Frontend API tests: 5 passed. TypeScript/production frontend build passed. Python lint and whitespace checks passed.
- CPU installer and CUDA worker batch prerequisite modes passed. Runtime build, packaging and smoke commands were exercised directly using the existing isolated environments; the entire new CUDA batch command and hosted workflow were not rerun end to end.
- CPU and CUDA frozen runtimes built successfully. Updated CPU runtime passed readiness, authenticated API/preferences, engine/decoder diagnostics and internal worker startup checks.
- Frozen CUDA worker executed a real CUDA kernel on NVIDIA GeForce RTX 4060 Ti, driver 610.88, Torch 2.6.0+cu124.
- End-to-end test used a locally trusted HTTPS manifest and all three real release parts. The frozen CPU parent downloaded 2,554,101,949 bytes, verified/extracted the worker, executed its GPU check, and activated CUDA.
- A real three-second stereo WAV Auto job completed with CPU fallback disabled. All six stems and the resulting package validated, with actual device `cuda`.
- Stopped the HTTPS host and restarted the frozen CPU backend: installed-file verification, offline CUDA activation and EOF shutdown passed.
- Playwright checked the Settings layout, unavailable-release message, NVIDIA details, and saving/reloading the automatic-download preference. Fixed delayed checkbox feedback found during that review. Browser console reported no errors. Local screenshots are ignored under `output/playwright/`.
- Candidate release files are under ignored `dist/cuda/`: `windows-cuda.json` and three archive parts (1 GiB, 1 GiB, 406,618,301 bytes). Assembled SHA-256: `634e6249e1504296cb34c010ba05506ab6fd151a92d6b78ed53b41f9d81d8c35`.

## Validation and release gates

- Follow-up: confirmed the default CUDA manifest endpoint returns HTTP 404 because the release assets have not been published. Added an explicit missing-release/file message for manifest and worker-part 404 responses; other HTTP failures retain their existing diagnostics. This message change does not make the downloads available and needs an installer rebuild to reach installed apps.

- The manifest and every archive part it lists must be published together to the `cuda-worker-v1` GitHub release before automatic downloads can succeed on other machines. No release assets were published in this session.
- The initial CUDA 12.4 worker does not cover every NVIDIA architecture (including RTX 50-series); newer runtimes require separate compatibility testing.
- Clean-machine installation, release signing, hosted workflow execution and broader GPU/driver coverage remain release gates. The existing CPU installer must be rebuilt to include these application changes; this session validated the new frozen CPU backend directly.
