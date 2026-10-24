<p align="center">
  <img src="desktop/src-tauri/icons/128x128.png" width="80" alt="ViiB StemLab icon">
</p>

<h1 align="center">ViiB StemLab</h1>

<p align="center">
  <strong>Build your stem library before the set.</strong><br>
  Turn your tracks into vocals, drums, bass and other.<br>
  Prepare locally, keep your library organized, and bring every layer into your mix.
</p>

<p align="center">
  <a href="https://github.com/ajbergh/ViiB-StemLab/releases/tag/v0.3.0"><strong>Download 0.3.0</strong></a>
  · <a href="#get-stemlab">Choose your installer</a>
  · <a href="docs/README.md">Documentation</a>
</p>

![StemLab's library showing six real four-stem packages, their durations and successful validation.](docs/images/stemlab-library.png)

## Your music, ready in layers

StemLab prepares portable stem packages for [ViiB MediaHub](https://github.com/ajbergh/ViiB-MediaHub). Add your music, let the queue work through it, and keep the results ready for your next session. Audio processing runs on your machine.

**Vocals · Drums · Bass · Other**

- **Prep a whole folder.** Add WAV, FLAC, MP3 or OGG files and follow each song through a persistent queue with progress, cancellation and retry controls.
- **Keep songs moving.** Process one, two or three songs at a time. Choose the concurrency that fits your machine.
- **Use your hardware.** Run on CPU, use optional NVIDIA acceleration on Windows, or Metal/MPS on supported Apple Silicon Macs.
- **Work offline.** Full includes the CPU engine and model. On-demand downloads verified components once and caches them for reuse.
- **Choose your output.** Save four aligned WAV stems, or use OGG/MP3 to save library space.
- **Know what is ready.** Browse your packages and validate them from the library before adding them to MediaHub.

## Get StemLab

| Platform | Full — engine and model included | On-demand — smaller download |
| --- | --- | --- |
| **Windows x64** | [Download Full](https://github.com/ajbergh/ViiB-StemLab/releases/download/v0.3.0/ViiB-StemLab_0.3.0_x64-full-setup.exe) | [Download On-demand](https://github.com/ajbergh/ViiB-StemLab/releases/download/v0.3.0/ViiB-StemLab_0.3.0_x64-ondemand-setup.exe) |
| **Apple Silicon · macOS 14+** · experimental | [Download Full DMG](https://github.com/ajbergh/ViiB-StemLab/releases/download/v0.3.0/ViiB-StemLab_0.3.0_arm64-full.dmg) | [Download On-demand DMG](https://github.com/ajbergh/ViiB-StemLab/releases/download/v0.3.0/ViiB-StemLab_0.3.0_arm64-ondemand.dmg) |
| **Linux x64 · Debian package** · experimental | [Download Full DEB](https://github.com/ajbergh/ViiB-StemLab/releases/download/v0.3.0/ViiB-StemLab_0.3.0_amd64-full.deb) | [Download On-demand DEB](https://github.com/ajbergh/ViiB-StemLab/releases/download/v0.3.0/ViiB-StemLab_0.3.0_amd64-ondemand.deb) |

Choose **Full** to get the CPU engine, decoders and model together. Choose **On-demand** for a smaller installer that downloads those components during setup. Windows GPU acceleration is a separate optional download with either installer. No separate Python installation is needed.

[All downloads, SHA-256 checksums and release notes](https://github.com/ajbergh/ViiB-StemLab/releases/tag/v0.3.0) · [Installer guide](docs/INSTALLERS.md)

<details>
<summary><strong>Platform notes</strong></summary>

- Windows installers are unsigned. Both CUDA profiles have been tested on an RTX 4060 Ti; other NVIDIA hardware and driver combinations remain unverified. See [GPU compatibility](docs/GPU_PLATFORMS.md).
- Apple Silicon builds require macOS 14+. They are experimental and ad-hoc signed without Developer ID notarization, so Gatekeeper may block opening them. Intel Mac builds are not included.
- Linux packages target x64 Debian systems with an Ubuntu 22.04 build baseline and CPU processing. Other distributions, ARM64, AppImage and RPM are not covered. See [Linux installation](docs/LINUX_PACKAGING.md).
- Clean-machine GUI installation and broader hardware testing remain unverified. Read the [release validation record](docs/RELEASE_0_3_0_PROGRESS.md) for the exact coverage.

</details>

## From track to library

1. **Add your music.** Drop files or folders into the desktop app, or use the native file picker.
2. **Set your preferences.** Choose an output folder, stem format and processing device. Adjust simultaneous songs to suit your machine.
3. **Generate and verify.** Follow the queue, browse the finished packages, and bring them into MediaHub.

![StemLab queue showing real demo tracks, CUDA processing progress and queue controls.](docs/images/stemlab-queue.png)

Screenshots show the browser-hosted interface with generated demo audio and real CUDA-separated packages. The desktop app adds native file dialogs and drag-and-drop.

## Prepare once, keep the results

Each `.viibstems` package carries four aligned stems and the information MediaHub needs to use them. StemLab can be closed while you play completed packages in MediaHub. Existing six-stem packages remain readable; new 0.3.0 generation uses the four-stem `htdemucs_ft` model.

WAV is the default. OGG and MP3 are lossy, use less disk space, and require a MediaHub version that supports `compressed-stems-v1`. [Learn about the package format](docs/VIIB_STEM_PACKAGE_V1.md).

## Explore further

- [Development and CLI reference](docs/DEVELOPMENT.md) — source setup, batch commands, model management and package tools.
- [Documentation index](docs/README.md) — architecture, workflows and integration details.
- [Standalone desktop development](docs/STANDALONE_DESKTOP.md) — native builds and runtime lifecycle.
- [Roadmap](ROADMAP.md) — what is implemented and what comes next.
