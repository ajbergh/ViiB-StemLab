# ViiB-StemLab

ViiB-StemLab is a local-first stem preparation application for the ViiB ecosystem.

Its job is deliberately narrow: **separate audio ahead of time, validate the result, and write portable ViiB Stem Packages that ViiB MediaHub can use later during DJ playback.**

StemLab is not part of the live DJ audio path. ViiB MediaHub must be able to play completed stem packages when StemLab is closed or not installed.

## Current status

Phase 0 (repository foundation) is complete. Phase 1 (ViiB Stem Package v1 contract) is in progress pending independent MediaHub conformance.

Implemented:

- Python 3.12 package layout;
- lightweight CLI;
- ViiB Stem Package v1 draft types and JSON Schema;
- deterministic cross-platform valid/invalid conformance fixtures;
- SHA-256 hashing;
- WAV geometry inspection;
- package validation and path-safety checks;
- atomic package assembly from six aligned stem files;
- packaging of externally generated six-stem WAV directories;
- separation-engine protocol;
- optional Demucs `htdemucs_6s` provider;
- CPU/CUDA/MPS capability detection;
- synchronous generation service;
- fast Windows/macOS/Linux CI that does not download model weights.

Not implemented yet:

- production queue;
- persistent worker;
- cancellation;
- desktop UI;
- self-contained runtime packaging;
- FLAC package output;
- MediaHub launch/deep-link integration.

See [ROADMAP.md](ROADMAP.md) for the full implementation plan.

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

Generate a package:

```bash
viib-stemlab generate "/path/to/track.flac" --output "/path/to/ViiB Stems"
```

Force a device if needed:

```bash
viib-stemlab generate track.flac --output stems --device cpu
viib-stemlab generate track.flac --output stems --device cuda
viib-stemlab generate track.flac --output stems --device mps
```

The first Demucs run may download model weights. StemLab records the engine, model, version, and actual device in the package manifest.

A separate **Demucs Smoke** GitHub Actions workflow is available for manually exercising the real `htdemucs_6s` CPU path. It is intentionally `workflow_dispatch` only so normal pull requests never download Torch or model weights.

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

The draft package contract is documented in [docs/VIIB_STEM_PACKAGE_V1.md](docs/VIIB_STEM_PACKAGE_V1.md), with a machine-readable schema in [docs/viib-stem-package-v1.schema.json](docs/viib-stem-package-v1.schema.json). Shared conformance fixtures live under [fixtures/](fixtures/).

## Design rule

The project should preserve this boundary even if the separation technology changes:

> **StemLab owns generation. MediaHub owns performance.**

A future ONNX or other inference engine should be able to replace Demucs without requiring a new DJ playback architecture, as long as it emits a compatible ViiB Stem Package.
