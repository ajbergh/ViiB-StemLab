# Development and CLI reference

Run these commands from the repository root. For desktop downloads and the product overview, see the [main README](../README.md).

## Architecture

```text
local audio
    |
    v
ViiB-StemLab
    |
    +-- Demucs / future engine
    +-- CPU / CUDA / MPS
    +-- validation
    |
    v
<track>-<hash>.viibstems/
    manifest.json
    vocals.wav
    drums.wav
    bass.wav
    other.wav
    |
    v
ViiB MediaHub DJ Mode
```

The filesystem package is the stable integration boundary. StemLab and MediaHub do not share a database or require a local service to remain running.

## Development

### Requirements

- Python 3.12 or 3.13
- `uv` is recommended, though normal `pip` editable installs also work

Create a lightweight development environment:

```bash
uv sync --extra dev
```

or:

```bash
python -m pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest
```

Run lint:

```bash
ruff check .
```

Run the CLI:

```bash
python -m viib_stemlab doctor
```

or, after installation:

```bash
viib-stemlab doctor
```

## Optional Demucs runtime

The normal test suite intentionally does not install PyTorch or download model weights.

For local generation development:

```bash
uv sync --extra dev --extra demucs
```

Then check the runtime:

```bash
viib-stemlab doctor
```

Generate a package from WAV, FLAC, MP3, or OGG:

```bash
viib-stemlab generate "/path/to/track.flac" --output "/path/to/ViiB Stems"
viib-stemlab generate "/path/to/track.mp3" --output "/path/to/ViiB Stems"
viib-stemlab generate "/path/to/track.ogg" --output "/path/to/ViiB Stems"
```

StemLab treats extensions case-insensitively. Demucs 4.1 tries sphn first and falls back to FFmpeg for unsupported input formats. For the most portable MP3/OGG behavior across Windows, macOS, and Linux, install FFmpeg and confirm both tools are visible with `viib-stemlab doctor`.

Force a device if needed:

```bash
viib-stemlab generate track.flac --output stems --device cpu
viib-stemlab generate track.flac --output stems --device cuda
viib-stemlab generate track.flac --output stems --device mps
```

Generation options:

```bash
# Automatically retry on CPU if GPU runs out of VRAM (cuda_oom) or fails
viib-stemlab generate track.flac --output stems --device cuda --fallback-to-cpu

# Specify a custom directory for model weight caches
viib-stemlab generate track.flac --output stems --cache-dir /path/to/cache

# Bypass disk-space preflight checks if operating with known tight storage margins
viib-stemlab generate track.flac --output stems --skip-preflight
```

The first Demucs run will check for cached model weights and download them if needed. StemLab records the engine, model, version, and actual device (including fallback) in the package manifest.

Cancellation (programmatic or via Ctrl+C) gracefully terminates the Demucs worker subprocess, purges `.partial-*` staging and temporary workspaces, and cleans up GPU VRAM allocations.

## Model management

Check model cache status and download weights ahead of time without initiating a separation job:

```bash
# List known models and their local cache status
viib-stemlab model status

# Pre-fetch weights into the local cache with progress reporting
viib-stemlab model download htdemucs_ft
```

## Durable queue & batch processing

Queue and process batches of audio files with configurable concurrency. Choose a limit suited to your memory and VRAM. Backed by a persistent SQLite WAL database with crash recovery and deduplication:

```bash
# Ingest individual tracks or recursive album directories
viib-stemlab queue add /path/to/music/ --output /path/to/ViiB-Library/

# Inspect queue status (supports JSON formatting)
viib-stemlab queue list
viib-stemlab queue list --status queued
viib-stemlab queue list --json

# Start processing queued tracks sequentially
viib-stemlab queue start

# Or process two songs at a time (choose 1, 2 or 3)
viib-stemlab queue start --concurrency 2

# Cancel, retry, or remove jobs
viib-stemlab queue cancel <job_id>
viib-stemlab queue retry <job_id>
viib-stemlab queue remove <job_id>

# Clear finished or failed jobs
viib-stemlab queue clear
```

## Desktop UI shell

ViiB-StemLab includes a modern desktop user interface built with React 19, TypeScript, and Tailwind CSS (matching the design system of `ViiB-MediaHub`).

To start the UI server:

```bash
# Launch the desktop UI server and open the browser automatically
viib-stemlab ui

# Custom port without opening the default browser
viib-stemlab ui --port 8765 --no-browser
```

Features:
- **Audio DropZone**: Drag-and-drop individual audio files (WAV, FLAC, MP3, OGG) or entire folder structures.
- **Visual Queue Monitor**: Real-time percentage progress bars, stage indicators (`preparing`, `separating`, `packaging`, `validating`), and cancel/retry/remove actions.
- **Stem Package Library**: Browse completed `.viibstems` packages with duration, size, stem pills, and one-click package manifest verification.
- **Engine Settings & Doctor**: Configure default stem library path, model selector (`htdemucs_ft` 4-stem), compute hardware preference (CUDA, MPS, CPU), CPU fallback toggle, model weight cache management, and hardware diagnostics.
- **Tauri Shell**: Native launcher in `desktop/src-tauri` with bundled-backend lifecycle and platform installers.

A separate **Demucs Smoke** GitHub Actions workflow is available for manually exercising the real `htdemucs_ft` CPU path with WAV, MP3, and OGG inputs. It is intentionally `workflow_dispatch` only so normal pull requests never download Torch or model weights.

The first real smoke run passed on 2026-09-24 using Demucs 4.0.1 and PyTorch 2.6.0 on CPU, producing six aligned 44.1 kHz stereo stems and a package that passed source/hash/geometry validation. See [docs/PHASE2_DEMUCS_SMOKE.md](PHASE2_DEMUCS_SMOKE.md) and [docs/PHASE3_ROBUST_GENERATION.md](PHASE3_ROBUST_GENERATION.md).

The 0.3.0 runtime uses **htdemucs_ft**, with Demucs pinned to **4.1.0**. The default `htdemucs_ft` bundle uses a pinned
Hugging Face revision with one YAML definition and four safetensors checkpoints.
StemLab verifies their full hashes and shares the offline cache between CPU and
CUDA workers. Existing `.th` files do not satisfy this new model setup.

## Package tools

Build a ViiB package from an existing four-stem WAV directory without running Demucs:

```bash
viib-stemlab package build \
  --source track.flac \
  --stems-dir "/path/to/existing-stems" \
  --output "/path/to/ViiB Stems" \
  --engine external \
  --model external-four-stem \
  --model-version unknown
```

The stems directory must contain `vocals.wav`, `drums.wav`, `bass.wav`, and `other.wav`. Complete legacy six-stem directories with `guitar.wav` and `piano.wav` are also accepted. This path is useful for interoperability testing and future StemDeck/third-party adapters.

Inspect:

```bash
viib-stemlab package inspect "track-abc123.viibstems"
```

Validate:

```bash
viib-stemlab package validate "track-abc123.viibstems"
```

Validate against the original source hash:

```bash
viib-stemlab package validate "track-abc123.viibstems" --source track.flac
```

Upgrade packages written by StemLab 0.1.0, which MediaHub rejects with `manifest.stemLayout is required`. Only `manifest.json` is rewritten (the original is kept as `manifest.v0.json`); stem audio is untouched:

```bash
viib-stemlab package upgrade "D:\Stems" --dry-run
viib-stemlab package upgrade "D:\Stems"
```

Then run a Stem Library scan in MediaHub.

The package contract is documented in [docs/VIIB_STEM_PACKAGE_V1.md](VIIB_STEM_PACKAGE_V1.md) and follows the MediaHub v1 consumer contract, with a machine-readable schema in [docs/viib-stem-package-v1.schema.json](viib-stem-package-v1.schema.json). Shared conformance fixtures live under [fixtures/](../fixtures/).

## Design rule

The project should preserve this boundary even if the separation technology changes:

> **StemLab owns generation. MediaHub owns performance.**

A future ONNX or other inference engine should be able to replace Demucs without requiring a new DJ playback architecture, as long as it emits a compatible ViiB Stem Package.

## Stem output format

Choose **Stem Export Format** in Settings before adding tracks, or pass
`--output-format ogg` / `--output-format mp3` to `generate`, `package build`, or
`queue add`. WAV is the default.

```powershell
viib-stemlab generate song.flac --output ./library --output-format mp3
```

Only the selected format is saved: four `.mp3`, `.ogg` (Vorbis), or `.wav` files
at the root of the `.viibstems` package. Compressed output has no saved WAV copies
or `exports/` folder. Temporary separator WAVs are removed when the job ends.
All stems are listed in the manifest with their encoded-file checksums.

OGG and MP3 are lossy. They use less disk space and require a MediaHub version
supporting `compressed-stems-v1`; older versions reject these packages safely.
Existing WAV packages continue to work. MP3 output includes gapless metadata to
preserve the source timeline and compensate encoder delay and padding in MediaHub.

Encoding uses FFmpeg (`libmp3lame`, VBR quality 2; `libvorbis`, quality 6), falling
back to SoundFile/libsndfile at its default quality if those encoders are absent.
Compressed validation requires SoundFile/libsndfile (`soundfile>=0.13`, included
with the separator runtime). Minimal installations can use `pip install 'viib-stemlab[audio]'`.
Files are decoded to verify codec, rate, channels, and exact frame count before
atomic promotion. Encoding or validation failure preserves an existing package.
