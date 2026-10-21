# Full and On-demand Windows installers

Both installers provide the same graphical application. They use the same app
identity and per-user settings, queue and model cache; they are alternative
installation choices, not separate applications to install side by side.

| Variant | Included | First launch |
| --- | --- | --- |
| Full | Native UI, Python/CPU engine, FFmpeg/FFprobe, six-stem model, notices, offline WebView2 installer | Verifies components, seeds the model cache and starts processing without a required download |
| On-demand | Native UI and online WebView2 setup | Offers a graphical download of the verified CPU engine/tools/model payload; afterward processing works offline |

CUDA acceleration remains an optional download in both variants, with the same
GPU detection, validation and CPU fallback. Full means complete **CPU processing**
offline, not all possible GPU runtimes. Automatic CUDA discovery can attempt an
optional network request when an NVIDIA driver is detected; it does not prevent
CPU processing offline.

## Build commands

From any working directory:

```bat
scripts\build_windows.bat
scripts\build_windows_full.bat
scripts\build_windows_ondemand.bat
```

The first command builds both. The others select one variant. Equivalent flags:
`scripts\build_windows.bat -Installer Full`, `OnDemand`, or `Both`. `-CheckOnly`
and `--help` are available. Prerequisites remain Python 3.12/3.13 x64, Node 22+,
Rust, Visual Studio C++ tools and Windows SDK. Internet is needed for uncached
build dependencies and the model. Close StemLab before building.

Build output:

- `dist/windows/ViiB StemLab_<version>_x64-full-setup.exe`
- `dist/windows/ViiB StemLab_<version>_x64-ondemand-setup.exe`
- A SHA-256 file beside each installer.
- `dist/components/windows-cpu.json` and the versioned CPU ZIP archive.

The shared payload includes exact per-file hashes, model provenance and dependency
notices. Model weights are verified using their complete SHA-256 before bundling.
Full uses the offline WebView2 installer; On-demand uses Tauri's WebView2 download
bootstrapper, which installs it only when needed. Both installers are currently
unsigned candidates.

## Publish the on-demand payload

Publish `windows-cpu.json` and the ZIP it names together to the GitHub release
`cpu-runtime-<version>` in `ajbergh/ViiB-StemLab` before distributing On-demand.
The app-version/platform/protocol and archive size/SHA-256 must match. Do not
replace an already published payload version. The candidate workflow builds and
uploads assets without publishing them. Full can be distributed independently
of the on-demand release endpoint.

For controlled testing or private HTTPS hosting, set `VIIB_STEMLAB_CPU_MANIFEST_URL`
before launching. `VIIB_STEMLAB_SETUP_CA_CERT` optionally adds a trusted PEM root
certificate for that host. TLS validation remains enabled; these are operator
overrides, not required end-user configuration. Public release assets must be
readable without a GitHub login.

## First-run setup and offline use

The setup screen runs through native Tauri commands and needs no Python. Downloads
show progress and disk requirements, support cancellation and retry, and are
staged under per-user app data. Failed or cancelled downloads are cleaned up.
Retry starts a fresh download. Existing cached components are checked before any
network request, so the On-demand app can restart offline after setup.

The native launcher verifies the archive and every inventory file, rejects unsafe
paths/links/duplicate entries, checks free disk space, seeds the model into the
shared `torch/hub/checkpoints` cache and runs a bounded engine/decoder probe before
activation. Promotion uses an atomic receipt and preserves prior generations.
The private backend starts afterward; the usual backend startup timeout does not
include download time. Logs are `setup-probe.log`, `backend-stderr.log` and
`desktop.log` in app data.

For manual runtime builds, run `packaging/prepare_cpu_payload.py --runtime <dir>`
after building the CPU backend and adding dependency inventories. Add
`--archive-output dist/components` to generate release assets. Plain
`npm --prefix desktop run package` builds Full and requires that prepared runtime;
On-demand uses `tauri.ondemand.conf.json` independently of the Full configuration.

To repeat native payload integration locally, run
`python packaging/smoke_installer_setup.py` after building. It requires Rust and
OpenSSL on the build machine and creates a temporary local HTTPS fixture without
adding any certificate to the system trust store. It tests Full offline setup,
download/probe, cached reuse, repair and corrupt-download rejection.

Clean-machine install/upgrade/uninstall testing, broader GPU validation, signing,
notice review and hosted CI remain release gates. See [progress](INSTALLER_PROGRESS.md).
