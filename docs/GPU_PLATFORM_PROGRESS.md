# GPU generations and Apple Silicon progress

- Created `feat/gpu-generations-macos` from released main.
- Current Windows worker is Torch 2.6 / CUDA 12.4; build/dependency pins and the
  download endpoint currently assume a single worker. The CPU parent must remain
  independent of upgraded GPU libraries.
- macOS engine selection exists, but release bootstrap currently bypasses setup
  on non-Windows platforms and hardcodes Windows filenames/platforms.
- Validation needs real separation in addition to capability detection. Available
  local accelerator: RTX 4060 Ti. RTX 20/30/50-series and MPS require other hardware.

## Implementation

- Added capability/driver-based legacy and modern worker profiles. Modern uses
  Torch 2.7.1 / CUDA 12.8, separate environments/staging/output, immutable v2 URLs,
  and compiled architecture checks that work on CPU-only packaging runners.
- Missing modern assets can fall back to legacy only for compatible architectures;
  Blackwell never falls back to the old worker. Existing cached workers stay offline.
- Candidate app version is 0.2.0, with new versioned payload endpoints, so released
  0.1.0 processing archives are not replaced. Health/UI versions follow package metadata.
- Made native setup platform-aware for macOS ARM64, including Unix executable
  permission restoration, inventory verification and shared model seeding.
- Added macOS Full/On-demand DMG build scripts, standalone source-built decoders,
  signing/notarization hooks, hosted packaging and physical-MPS validation workflows.
- MPS detection executes a real Metal kernel. Added MPS memory diagnostics and
  cache cleanup; operator CPU fallback is passed to the subprocess explicitly.
- Improved Windows runtime activation: move to an inactive generation before GPU
  probing and atomically publish the receipt only after success. Retry transient
  image/scanner locks while respecting cancellation.
- Local full Python suite: 155 passed. Focused architecture/manifest/MPS/payload
  tests pass; Ruff passes. Native Windows tests: 5 passed, 1 fixture test ignored.
  Frontend tests: 5 passed; production build passed before the final metadata import.
- Modern frozen worker built successfully. Real CUDA kernel and six-stem separation
  passed on RTX 4060 Ti / Torch 2.7.1+cu128 with fallback disabled and a validated
  package recording `device=cuda`. Archive: 3,282,412,134 bytes, expanded
  5,190,154,773; assembled SHA-256
  `719bc178bdff6fd8823b81181e511d224027767b5a524a9af2bd8440e054e521`.
- Final frontend metadata import build, native tests, lint and lock checks passed.
- Added final-DMG mount, outer signature, resource/flavor and payload inventory
  checks. Native setup integration uses the finished Full DMG's copied resources.
- User confirmed no physical Apple Silicon Mac is currently available: build
  candidates first. RTX 20/30/50 and physical MPS validation remain unverified.
- Updated frozen CPU parent downloaded all real modern worker parts via a temporary
  trusted HTTPS fixture, verified/extracted the worker, and activated its GPU probe.
  A real Auto job completed with CPU fallback disabled; all six stems/package
  validated and the manifest recorded CUDA. With the HTTPS host stopped, installed
  file verification, GPU probing, cached activation and clean EOF shutdown passed.
- Hosted macOS candidate build is running in draft PR #7. Final DMG inspection,
  compressed-audio CPU separation, native setup/repair and platform checks are the
  remaining hosted validation. [Build/validation guide](GPU_PLATFORMS.md).
- The initial source checks passed on Windows, Linux and macOS. Final frontend
  platform-card changes compile successfully. Registry retries are now bounded,
  with npm audit omitted during candidate installation to avoid delaying builds.
- Hosted ARM64 Full/On-demand DMGs built and passed mounted signature/flavor and
  exact payload checks. Native tests and frozen CPU FLAC separation passed. The
  HTTPS fixture failed macOS TLS policy because its certificate lacked serverAuth
  EKU; added that extension and rerunning the complete candidate workflow.
