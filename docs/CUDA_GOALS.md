# Downloadable CUDA acceleration

- [x] Keep the CPU installer self-contained and usable offline after model setup.
- [x] Detect NVIDIA hardware independently of the bundled CPU Torch build.
- [x] Automatically prepare a compatible, separately published CUDA worker; allow disabling, cancellation, and retry in Settings.
- [x] Verify the release manifest, exact archive size/SHA-256, safe extraction, installed files, and actual GPU execution before selecting CUDA.
- [x] Share model weights, preserve CPU fallback and cancellation, and report the device actually used.
- [x] Provide Windows worker build/release tooling and tests; validate physical GPU execution locally.
- [ ] Rebuild the distributed desktop installer and publish the manifest and worker parts after release review.
