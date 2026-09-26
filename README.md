# ViiB-StemLab

ViiB-StemLab is a local-first stem preparation application for the ViiB ecosystem.

Its job is deliberately narrow: **separate audio ahead of time, validate the result, and write portable ViiB Stem Packages that ViiB MediaHub can use later during DJ playback.**

StemLab is not part of the live DJ audio path. ViiB MediaHub must be able to play completed stem packages when StemLab is closed or not installed.

## Current status

Phase 0 (repository foundation), Phase 1 (ViiB Stem Package v1 contract, StemLab side), Phase 2 (Demucs MVP), Phase 3 (Robust Generation), Phase 4A (Durable Queue & Batch Engine), and Phase 4B (Desktop UI Shell) are complete. The package contract is waiting on independent MediaHub conformance before final freeze.


Implemented:

- Python 3.12/3.13 package layout;
- lightweight CLI with rich diagnostics;
- ViiB Stem Package v1 draft types and JSON Schema;
- deterministic cross-platform valid/invalid conformance fixtures;
- SHA-256 hashing;
- WAV geometry inspection;
- package validation and path-safety checks;
- atomic package assembly from six aligned stem files;
- packaging of externally generated six-stem WAV directories;
- separation-engine protocol;
- Demucs `htdemucs_6s` provider behind an optional heavyweight runtime extra;
- CPU/CUDA/MPS capability detection;
- synchronous generation service;
- explicit WAV, FLAC, MP3, and OGG source-file support;
- real `htdemucs_6s` CPU smoke generation and package validation;
- programmatic job cancellation via `CancellationToken` with subprocess termination and `.partial-*` directory cleanup;
- host GPU VRAM and IPC cleanup (`cleanup_vram`);
- disk-space preflight estimation and filesystem capacity verification (`check_disk_space`);
- structured failure classification (`StemLabError` hierarchy with user diagnostics and exit-code parsing);
- explicit GPU-to-CPU fallback policy (`--fallback-to-cpu`) with automatic retry and manifest device provenance;
- model cache preflight, verification, and management (`ModelCacheManager`, `model status`, `model download`);
- typed structured progress emission (`ProgressUpdate`);
- overwrite-promotion rollback coverage;
- durable SQLite WAL persistent queue with crash recovery (`QueueStore`);
- audio directory scanning and duplicate detection (`discover_audio_files`, `ingest_paths`);
- headless background queue worker coordinator (`QueueRunner`);
- full CLI command suite for batch queue management (`viib-stemlab queue`);
- desktop UI server with zero external web dependencies (`viib-stemlab ui`);
- modern React 19 + TypeScript + Vite + Tailwind desktop user interface matching `ViiB-MediaHub` design system;
- completed `.viibstems` package library browser with live contract verification;
- Tauri v2 native desktop shell scaffolding;
- detailed PyTorch/CUDA/MPS, model cache, and disk space reporting in `doctor`;
- fast Windows/macOS/Linux CI that does not download model weights.

Not implemented yet:

- self-contained runtime packaging / installer;
- FLAC package output;
- MediaHub launch/deep-link integration;
- real CUDA and Apple MPS end-to-end smoke coverage in CI.

See [ROADMAP.md](ROADMAP.md) for the full implementation plan.

## Documentation

- [ROADMAP.md](ROADMAP.md) — implementation phases, architecture decisions, and current status.
- [docs/README.md](docs/README.md) — documentation index.
- [docs/VIIB_STEM_PACKAGE_V1.md](docs/VIIB_STEM_PACKAGE_V1.md) — human-readable package contract.
- [docs/viib-stem-package-v1.schema.json](docs/viib-stem-package-v1.schema.json) — machine-readable v1 manifest schema.
- [docs/PHASE2_DEMUCS_SMOKE.md](docs/PHASE2_DEMUCS_SMOKE.md) — first real Demucs end-to-end validation record.
- [docs/PHASE3_ROBUST_GENERATION.md](docs/PHASE3_ROBUST_GENERATION.md) — Phase 3 robust generation architecture and specification.
- [docs/PHASE4_QUEUE_ENGINE.md](docs/PHASE4_QUEUE_ENGINE.md) — Phase 4A durable queue engine architecture and CLI reference.
- [docs/PHASE4_DESKTOP_UI.md](docs/PHASE4_DESKTOP_UI.md) — Phase 4B Desktop UI architecture, REST API, and component guide.
- [fixtures/README.md](fixtures/README.md) — shared positive/negative conformance fixtures.

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
    guitar.wav
    piano.wav
    other.wav
    |
    v
ViiB MediaHub DJ Mode
```

The filesystem package is the stable integration boundary. StemLab and MediaHub do not share a database or require a local service to remain running.

## Development

### Requirements

- Python 3.12
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

StemLab treats extensions case-insensitively. Demucs tries FFmpeg/FFprobe first and can fall back to torchaudio for decoding. For the most portable MP3/OGG behavior across Windows, macOS, and Linux, install FFmpeg and confirm both tools are visible with `viib-stemlab doctor`.

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
viib-stemlab model download htdemucs_6s
```

## Durable queue & batch processing

Queue and process batches of audio files without overloading GPU VRAM. Backed by a persistent SQLite WAL database with crash recovery and deduplication:

```bash
# Ingest individual tracks or recursive album directories
viib-stemlab queue add /path/to/music/ --output /path/to/ViiB-Library/

# Inspect queue status (supports JSON formatting)
viib-stemlab queue list
viib-stemlab queue list --status queued
viib-stemlab queue list --json

# Start processing queued tracks sequentially
viib-stemlab queue start

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
- **Engine Settings & Doctor**: Configure default stem library path, model selector (`htdemucs_6s` 6-stem or `htdemucs` 4-stem), compute hardware preference (CUDA, MPS, CPU), CPU fallback toggle, model weight cache management, and hardware diagnostics.
- **Tauri Shell**: Scaffolding in `desktop/src-tauri` for native desktop window distribution.

A separate **Demucs Smoke** GitHub Actions workflow is available for manually exercising the real `htdemucs_6s` CPU path with WAV, MP3, and OGG inputs. It is intentionally `workflow_dispatch` only so normal pull requests never download Torch or model weights.

The first real smoke run passed on 2026-09-24 using Demucs 4.0.1 and PyTorch 2.6.0 on CPU, producing six aligned 44.1 kHz stereo stems and a package that passed source/hash/geometry validation. See [docs/PHASE2_DEMUCS_SMOKE.md](docs/PHASE2_DEMUCS_SMOKE.md) and [docs/PHASE3_ROBUST_GENERATION.md](docs/PHASE3_ROBUST_GENERATION.md).

## Package tools

Build a ViiB package from an existing six-stem WAV directory without running Demucs:

```bash
viib-stemlab package build \
  --source track.flac \
  --stems-dir "/path/to/existing-stems" \
  --output "/path/to/ViiB Stems" \
  --engine external \
  --model external-six-stem \
  --model-version unknown
```

The stems directory must contain `vocals.wav`, `drums.wav`, `bass.wav`, `guitar.wav`, `piano.wav`, and `other.wav`. This path is useful for interoperability testing and future StemDeck/third-party adapters.

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

The package contract is documented in [docs/VIIB_STEM_PACKAGE_V1.md](docs/VIIB_STEM_PACKAGE_V1.md) and follows the MediaHub v1 consumer contract, with a machine-readable schema in [docs/viib-stem-package-v1.schema.json](docs/viib-stem-package-v1.schema.json). Shared conformance fixtures live under [fixtures/](fixtures/).

## Design rule

The project should preserve this boundary even if the separation technology changes:

> **StemLab owns generation. MediaHub owns performance.**

A future ONNX or other inference engine should be able to replace Demucs without requiring a new DJ playback architecture, as long as it emits a compatible ViiB Stem Package.
