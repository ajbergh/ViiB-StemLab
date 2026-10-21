# Windows 0.1.0 release goals

- [x] Validate source checks and synchronize dependency lock metadata.
- [x] Validate packaged CUDA execution with CPU fallback disabled.
- [x] Open and merge the standalone desktop PR after hosted checks pass.
- [x] Build CPU payload, Full/On-demand installers and CUDA worker from the merged commit.
- [x] Verify release payload checksums and real GPU execution.
- [x] Publish CPU and CUDA runtime releases and verify anonymous public downloads.
- [x] Verify Full and On-demand application startup against public runtime downloads.
- [x] Publish application installers, checksums and clear compatibility notes.

## Scope and limitations

Windows x64; initial CUDA worker uses Torch 2.6 / CUDA 12.4. Validate on the
available RTX 4060 Ti; do not imply coverage of RTX 50-series or other untested
architectures. No signing certificate is configured: identify unsigned installers
explicitly. Clean-machine and broad hardware coverage must be stated honestly.
