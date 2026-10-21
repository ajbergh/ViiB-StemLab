# Installer variants progress

## Implementation

- Confirmed that backend-first startup must be split so a native setup screen works before Python exists.
- Added one verified CPU/tools/model payload used locally by Full and downloaded by On-demand. The model's complete SHA-256 is pinned independently of the release inventory.
- Added native setup commands, progress, cancellation, retry, TLS-only downloads, free-space checks, safe extraction, complete file inventories, model-cache seeding, engine probes and atomic activation. Cached generations are verified before any network request.
- Added separate Tauri resource/WebView2 configurations and batch entry points. The default Windows builder produces both installers, checksums and on-demand release assets. Both share the same app identity and user state; CUDA remains optional.
- Added bounded retries and restoration of the previous runtime for Windows staging moves after a transient lock was observed locally.
- Corrected an HTTP-client blocking-adapter timer issue found by the real HTTPS integration test; setup downloads now use a dedicated Tokio runtime.
- Native GUI validation exposed a Windows lock when renaming a directory after its engine probe. Setup now moves into an inactive generation before probing, retries transient Windows activation locks, and activates the receipt only after the probe succeeds. Stalled HTTP requests are cancellable; app shutdown waits for setup cleanup.
- The builder now compiles the common native executable once and uses Tauri's bundle-only command for the two resource/WebView2 configurations.

## Validation

- Python: 139 passed, including new CPU-payload inventory/model/checksum tests. Frontend API tests: 5 passed; production TypeScript/Vite build passed.
- Native unit tests: 5 passed. The separately invoked real-payload integration test also passed Full offline setup/model seeding, HTTPS download and engine probe, offline reuse with an unreachable manifest URL, repair of a deleted cached executable, and rejection of a corrupt archive hash without activation. It was repeated successfully after the final Windows lock/cancellation fixes.
- The complete `scripts/build_windows.bat -Installer Both` command succeeded with one common native compilation and two bundle-only packaging passes. Both final candidates contain the identical native executable and the intended different resource sets.
- Extracted the On-demand candidate without installing it and launched its native WebView with Python absent from PATH and no CPU runtime installed. The setup screen, download action and failed-download retry state worked; WebView console showed no errors.
- Focused repository review found no remaining concrete high-impact lifecycle/packaging issue.
- Final native On-demand GUI: real HTTPS download cancellation reached a clean Retry state; retry activated the engine and opened Settings with `Audio model ready`. No Python was present on PATH. The final move-before-probe activation succeeded.
- Stopped the HTTPS fixture and restarted On-demand against an unreachable manifest URL: cached verification, engine startup and model readiness passed. A real three-second stereo WAV then completed CPU six-stem separation and package validation with fallback disabled.
- Final native Full GUI opened with fresh user state, an unreachable download URL and Python absent from PATH. Model-cache seeding and engine startup completed without a processing download. WebView consoles reported no errors. Screenshots are ignored under `output/playwright/`.
- Both installer contents were extracted for inspection without registering/installing software on the machine. Full includes the checkpoint, runtime/tools and offline WebView2 installer; On-demand has no processing runtime. Native QA windows and the local HTTPS fixture were closed afterward.

## Initial installer candidate artifacts — 2026-10-21

| File under `dist/windows/` | Bytes | SHA-256 |
| --- | ---: | --- |
| `ViiB StemLab_0.1.0_x64-full-setup.exe` | 488,401,482 (about 466 MiB) | `fde6722238e37bd70e64ec33954570947235f62876526d0095397d2a32c8bc50` |
| `ViiB StemLab_0.1.0_x64-ondemand-setup.exe` | 2,462,415 (about 2.4 MiB) | `af071734fe4c3283225c9089e86e2ebfddbc2678f36f1504d3fd210a8aad8c76` |

- Checksum files were independently verified. Both signature statuses are `NotSigned`.
- `dist/components/stemlab-cpu-0.1.0-windows-x64.zip`: 299,120,337 bytes; SHA-256 `5e0f4aeee6be302c1ad049c08ae55a4daced51d9a41685c25399f985e109c092`.
- Matching manifest: `dist/components/windows-cpu.json`; unpacked payload 683,165,653 bytes. Generated binaries, model weights, state and screenshots remain ignored by Git.

## Release gates

The candidate evidence above predates the published rebuild. See
[release progress](RELEASE_PROGRESS.md) for the final public artifacts, current
checksums, and native CPU/CUDA tests against public download URLs.

- Follow-up: the On-demand first-run screen now displays the native setup failure directly in its alert, removing the misleading generic connection/disk-space instruction when the release is unpublished. Existing installers require a rebuild for this UI change; publishing the CPU manifest and archive is still required for public first-run downloads.

- CPU/CUDA runtime assets and both application installers are now published; public downloads were verified without authentication.
- The candidate workflow includes the native HTTPS/offline integration test. Final local batch builds and native integration passed, and hosted source CI passed. Existing frontend development dependency advisories remain separate work.
- Signing, clean-machine installation/uninstallation and broader platform validation remain separate release checks.
