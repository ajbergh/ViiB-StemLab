# GPU generations and Apple Silicon goals

- [x] Select NVIDIA workers by compute capability and driver, retaining the published legacy runtime.
- [x] Build an isolated pinned Blackwell-capable worker without replacing the CPU environment.
- [x] Make Full/On-demand payload setup platform-aware and preserve executable permissions on macOS.
- [x] Build and exercise Apple Silicon app/DMG variants with self-contained decoders and shared CPU/MPS runtime.
- [x] Require a real MPS kernel before advertising acceleration; improve MPS fallback/memory diagnostics.
- [x] Add platform packaging workflows, signing hooks and explicit hardware validation gates.
- [x] Run relevant source checks and actual GPU tests available on this machine; record remaining hardware limits.

Existing v0.1.0 release assets remain immutable. Hosted Apple Silicon CPU/MPS
separation is verified. RTX 20/30/50 hardware and clean-machine Mac installation
remain unverified.
