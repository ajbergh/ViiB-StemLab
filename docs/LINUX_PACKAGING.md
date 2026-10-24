# Linux x64 Debian candidates

Build natively on Ubuntu 22.04 x64 with Python 3.12/3.13, Node 22+, Rust,
build-essential, libwebkit2gtk-4.1-dev, libayatana-appindicator3-dev,
librsvg2-dev, patchelf, and libgomp1:

```sh
bash scripts/build_linux.sh --check-only
bash scripts/build_linux.sh
```

The builder creates Full and On-demand `.deb` packages and SHA-256 files under
`dist/linux/`. Full includes CPU Torch 2.6.0, Demucs 4.1.0, verified htdemucs_ft
safetensors, and minimal FFmpeg/FFprobe compiled from checksum-pinned source.
On-demand downloads the same verified payload. Both use the production native
bootstrap and preserve queue/settings/model state outside the installation.
Linux NVIDIA worker downloads are not supplied; this candidate uses CPU processing.

The CPU payload manifest `dist/linux-components/linux-x64.json` and its ZIP must
be published together under `linux-runtime-0.3.0` before distributing On-demand.
The workflow builds candidates only. It does not publish assets or install them
on users' systems. Runtime archives preserve executable modes and contain file
hashes, dependency inventories, decoder source/build information, and notices.

The Linux workflow inspects and extracts each finished Debian package, verifies
its flavor, architecture, runtime inventory and executable permissions, then
checks Full offline setup, HTTPS On-demand setup, cache reuse, repair, checksum
rejection, and real frozen CPU separation against the extracted Full resources.
System GTK/WebKitGTK libraries are declared Debian dependencies. Install with
`sudo apt install ./ViiB-StemLab_0.3.0_amd64-full.deb` (or the On-demand variant).
Only one flavor can be installed at once; both have the same package identity.

Ubuntu 22.04 x64 is the build baseline. Other distributions, ARM64, AppImage/RPM,
clean-machine desktop installation, and broad graphics-driver compatibility
remain unverified. Test GUI startup and native dialogs on target desktops before
claiming general Linux release readiness.
