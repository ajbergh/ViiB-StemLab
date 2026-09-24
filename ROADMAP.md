# ViiB-StemLab Roadmap

**Status:** Active implementation — Phase 0 complete; StemLab sides of Phase 1 and Phase 2 complete; MediaHub conformance gate pending  
**Repository:** `ajbergh/ViiB-StemLab`  
**Initial roadmap date:** 2026-09-24  
**Last documentation review:** 2026-09-24  
**Primary consumer:** ViiB MediaHub DJ Mode  
**Core principle:** **Separate ahead of time; perform in real time.**

ViiB-StemLab is a standalone, local-first application for preparing high-quality audio stems before DJ playback. It owns the heavy machine-learning generation workflow. ViiB MediaHub remains the performance application: it discovers, validates, indexes, and plays completed stem packages without requiring StemLab, Python, PyTorch, Demucs, or a GPU during a live set.

This repository is intentionally separate from ViiB MediaHub so model/runtime changes, GPU failures, large dependencies, and long-running generation jobs do not become part of MediaHub's mission-critical DJ audio path.

---

## 1. Product mission

ViiB-StemLab should make local stem preparation reliable enough to use before a professional DJ performance.

The target workflow is:

1. Add individual tracks, folders, or a preparation list.
2. StemLab identifies the best available compute device.
3. StemLab separates each track into six canonical stems.
4. StemLab validates the output.
5. StemLab atomically writes a versioned **ViiB Stem Package**.
6. ViiB MediaHub detects the completed package later.
7. MediaHub performs live stem playback from the pre-generated files.

The initial canonical stems are:

- vocals
- drums
- bass
- guitar
- piano
- other

MediaHub can derive its normal four-button performance layout without requiring StemLab to render separate files:

- **VOCAL** = vocals
- **DRUMS** = drums
- **BASS** = bass
- **MUSIC** = guitar + piano + other

StemLab is not part of MediaHub's live transport clock and should never need to remain running during playback.

---

## 2. Non-goals

The initial StemLab project is **not**:

- a real-time separation engine inside DJ playback;
- a replacement DJ application;
- a shared database service for ViiB MediaHub;
- a cloud stem-processing service;
- a requirement for MediaHub to start or play normal tracks;
- a reason to embed Python/PyTorch inside the MediaHub process;
- a promise to reproduce proprietary separation algorithms from commercial software.

StemLab may eventually offer preview and audition tools, but the first priority is deterministic generation of interoperable packages.

---

## 3. Architectural boundary with ViiB MediaHub

The integration boundary is a filesystem package contract, not a local REST service and not a shared database.

```text
Audio files
    |
    v
+-----------------------+
|     ViiB-StemLab      |
|                       |
|  queue / models       |
|  CUDA / MPS / CPU     |
|  separation           |
|  validation           |
+-----------+-----------+
            |
            | writes atomically
            v
   <id>.viibstems/
      manifest.json
      vocals.wav
      drums.wav
      bass.wav
      guitar.wav
      piano.wav
      other.wav
            |
            v
+-----------------------+
|   ViiB MediaHub       |
|                       |
| discover / validate   |
| index / stream        |
| DJ stem playback      |
+-----------------------+
```

MediaHub should be able to consume the package if StemLab is closed, uninstalled, upgraded, or replaced by another compatible generator.

That means the package specification is one of this repository's most important public interfaces.

---

# PART I — TECHNOLOGY STRATEGY

## 4. Initial runtime

### 4.1 Python core

Use **Python 3.12** for the initial generation core.

Reasons:

- the highest-quality practical open stem-separation models are currently centered on PyTorch;
- Demucs is already mature and widely exercised;
- CUDA and Apple MPS support are available through PyTorch;
- Python keeps the first implementation close to the reference model environment;
- the package contract keeps this runtime replaceable later.

Use a `src/` package layout and manage development environments with **uv** where practical.

### 4.2 Separation engine abstraction

Do not couple the application directly to one model forever.

Define an internal engine boundary similar to:

```python
class StemEngine(Protocol):
    def capabilities(self) -> EngineCapabilities: ...
    def separate(
        self,
        source: Path,
        work_dir: Path,
        *,
        device: str,
        progress: ProgressCallback | None = None,
    ) -> SeparationResult: ...
```

Initial provider:

- `DemucsEngine`

Possible future providers:

- ONNX-backed model
- newer Demucs-compatible model
- alternate open-source separator
- experimental pure-native provider

The rest of StemLab should work with canonical output stems and not care which inference engine produced them.

### 4.3 Initial model

The first production candidate is **Demucs `htdemucs_6s`**.

Expected outputs:

- vocals
- drums
- bass
- guitar
- piano
- other

The model choice must be recorded in every package manifest.

### 4.4 Device selection

Support:

- `auto`
- `cuda`
- `mps`
- `cpu`

For `auto`, prefer:

1. CUDA when a compatible NVIDIA runtime is available;
2. MPS on supported Apple Silicon;
3. CPU.

Explicit user choice should be honored, but failure behavior must be visible. A later milestone may optionally retry a failed GPU job on CPU; that fallback must never be silent.

---

## 5. Process isolation

Even though StemLab is its own application, model inference should still be isolated from the UI/control process where practical.

The initial CLI may execute Demucs as a subprocess. The desktop application should eventually use a managed persistent worker or equivalent isolation so:

- cancellation can terminate inference promptly;
- GPU memory is released after failure;
- a Torch/CUDA crash does not corrupt queue state;
- model warm-up can be reused for consecutive jobs;
- progress can be parsed without blocking the UI.

Do not optimize worker reuse before correctness, cancellation, and output validation are proven.

---

# PART II — VIIIB STEM PACKAGE V1

## 6. Package identity

Canonical package extension:

```text
.viibstems
```

Recommended package name:

```text
<safe-source-stem>-<source-sha256-prefix>.viibstems
```

Example:

```text
Human-9b83a2c148d1.viibstems/
```

The source hash, not the filename, is the authoritative identity check.

---

## 7. Package layout

Initial package layout:

```text
Human-9b83a2c148d1.viibstems/
    manifest.json
    vocals.wav
    drums.wav
    bass.wav
    guitar.wav
    piano.wav
    other.wav
```

WAV is the initial implementation format because Demucs already produces aligned WAV output and it avoids adding a transcode step before the package contract is proven.

Before the first stable release, benchmark FLAC for:

- disk savings;
- encode time;
- decode CPU;
- random seek behavior;
- MediaHub playback latency.

If FLAC becomes the default, the manifest contract must remain codec-explicit so old WAV packages continue to work.

---

## 8. Manifest requirements

The manifest must be versioned and self-describing.

Draft shape:

```json
{
  "schemaVersion": 1,
  "packageId": "Human-9b83a2c148d1",
  "createdAt": "2026-09-24T00:00:00Z",
  "source": {
    "filename": "Human.flac",
    "sha256": "9b83a2c148d1...",
    "sizeBytes": 123456789
  },
  "generator": {
    "name": "ViiB-StemLab",
    "version": "0.1.0"
  },
  "model": {
    "engine": "demucs",
    "name": "htdemucs_6s",
    "version": "4.0.1",
    "device": "cuda"
  },
  "audio": {
    "codec": "wav",
    "sampleRate": 44100,
    "channels": 2,
    "frames": 15664861,
    "durationSeconds": 355.21
  },
  "stems": {
    "vocals": {
      "file": "vocals.wav",
      "sha256": "...",
      "sizeBytes": 123,
      "frames": 15664861
    }
  }
}
```

The real manifest must contain all six canonical stem entries.

### 8.1 Required invariants

The current v1 validator enforces:

- `schemaVersion` is supported;
- all six canonical stems exist;
- file paths are package-relative and cannot traverse outside the package;
- checksums and byte sizes match;
- files are non-empty;
- sample rates match;
- channel counts match;
- frame counts match exactly;
- `durationSeconds` matches frames/sample rate;
- source SHA-256 and source size are present and can be verified when the original source is supplied;
- generator and model provenance is present.

Additional audio-quality checks such as reconstructed-mix comparison, clipping analysis, and sample-level quality metrics belong to the later quality/benchmark work and are not part of the current package-validity decision.

### 8.2 Forward compatibility

MediaHub and StemLab should use a conservative schema policy:

- unknown newer major schema => reject as unsupported;
- known schema with unknown optional fields => ignore optional fields;
- never reinterpret a field with different semantics under the same schema version.

The v1 schema should be frozen before the first public package-producing release.

---

## 9. Atomic package finalization

Never expose partial output as a completed package.

Generation flow:

```text
output library/
    .Human-<id>.partial-<uuid>/
        ...
             |
             | validate
             v
    Human-<id>.viibstems/
```

Requirements:

- write into a temporary directory on the same filesystem as the final package;
- validate all stems before promotion;
- write `manifest.json` only after stem metadata/checksums are known;
- fsync/flush where practical;
- atomically rename the temporary directory to the final package;
- never mark a package complete based only on process exit code;
- on cancellation/failure, remove the temporary directory.

Overwrite must be explicit.

---

# PART III — GENERATION PIPELINE

## 10. Pipeline stages

Initial stages:

1. validate request
2. hash source
3. resolve output target
4. resolve compute device
5. ensure engine/model availability
6. separate
7. collect canonical stem outputs
8. validate audio geometry
9. calculate checksums
10. write manifest
11. validate complete package
12. atomically finalize
13. report completion

Each stage should eventually emit structured progress.

---

## 11. Source handling

Current explicitly supported local source extensions:

- WAV
- FLAC
- MP3
- OGG

Extensions are matched case-insensitively. Demucs attempts FFmpeg/FFprobe decoding first and can fall back to torchaudio. `viib-stemlab doctor` reports whether FFmpeg and FFprobe are available so compressed-input failures are easier to diagnose.

Planned source-format expansion:

- M4A/AAC
- additional OGG-contained codecs where cross-platform decoding is verified

Do not add YouTube downloading to the first milestone. StemLab's primary purpose is processing audio the user already has locally.

Treat FFmpeg as an explicit runtime dependency when it is required for portable decoding or future package transcoding, with separate licensing/release documentation.

---

## 12. Queue

The desktop application eventually needs a durable preparation queue.

Each job should record:

- id
- source path
- source hash when available
- requested model
- requested device
- actual device
- output library
- status
- stage
- progress
- created time
- started time
- completed time
- error category
- diagnostic message
- package path on success

States:

- queued
- preparing
- separating
- validating
- finalizing
- complete
- failed
- cancelled

The first CLI implementation may remain synchronous. Queue persistence is a later phase after the package contract and engine path are proven.

---

## 13. Cancellation

Cancellation is a correctness feature, not UI polish.

A cancelled job must:

- stop active inference;
- terminate owned child processes;
- release GPU resources where possible;
- remove partial output;
- never produce a finalized package;
- leave enough diagnostics to understand what was cancelled.

A process crash or forced application exit should not leave a valid-looking package behind.

---

## 14. Failure classification

Normalize common failures:

- source_not_found
- source_unreadable
- unsupported_input
- model_missing
- model_download_failed
- cuda_unavailable
- cuda_oom
- mps_unavailable
- inference_failed
- worker_crashed
- cancelled
- output_missing
- output_geometry_mismatch
- checksum_failed
- disk_full
- permission_denied
- package_exists
- package_validation_failed

User-facing errors should be actionable while preserving the detailed internal diagnostic log.

---

# PART IV — CLI

## 15. Initial commands

The first scaffold should establish a useful headless interface.

### 15.1 Doctor

```text
viib-stemlab doctor
```

Reports:

- StemLab version
- Python version
- operating system/architecture
- Demucs availability
- Torch availability/version
- CUDA availability
- MPS availability
- selected auto device

### 15.2 Generate

```text
viib-stemlab generate <audio-file> --output <stem-library>
```

Options:

- `--model htdemucs_6s`
- `--device auto|cuda|mps|cpu`
- `--overwrite`
- later: quality/shifts
- later: output codec

### 15.3 Package validation

```text
viib-stemlab package validate <package.viibstems>
```

Optional:

```text
--source <original-audio-file>
```

When a source is supplied, verify the source SHA-256 against the manifest.

### 15.4 Inspect

```text
viib-stemlab package inspect <package.viibstems>
```

Print normalized manifest information for debugging and MediaHub interoperability work.

---

# PART V — DESKTOP APPLICATION

## 16. Desktop UX direction

Do not block core package work on the desktop shell.

Once the package/CLI path is proven, build the desktop app around the same core library.

Likely high-level screens:

### Queue

- drag/drop import
- Add Files
- Add Folder
- queue rows
- progress
- device/model
- cancel/retry

### Library

- completed packages
- source file
- model
- generated date
- disk size
- open package folder
- validate
- regenerate
- delete

### Preview

- original + six aligned stems
- mute/solo
- simple gain controls
- A/B original versus reconstructed mix
- waveform overview

### Settings

- default Stem Library
- default model
- compute device
- model storage
- concurrent jobs
- cleanup behavior
- diagnostics/log directory

A Tauri v2 shell is a strong candidate because it can keep the heavy Python runtime out of the renderer and has existing precedent in the StemDeck project. The final desktop choice should be made after the CLI/core boundary is stable.

---

# PART VI — PERFORMANCE AND QUALITY

## 17. Benchmark matrix

Measure generation on:

- Windows CPU
- Windows NVIDIA CUDA
- Apple Silicon MPS
- macOS CPU
- Linux CPU
- Linux NVIDIA CUDA

Track:

- model startup time
- model warm reuse time
- separation wall time
- real-time factor
- peak RAM
- peak VRAM
- output size
- package finalization time
- checksum time

---

## 18. Audio acceptance

For every generated package:

- all stems must begin on the same frame;
- all stems must have compatible frame count;
- no silent truncation;
- no NaN/Inf data;
- no corrupt files;
- no unexpected clipping introduced by packaging;
- stem sum/reconstruction should be checked on deterministic fixtures where possible.

For model-quality evaluation, maintain a lawful listening/benchmark corpus and compare new engine/model versions before changing defaults.

Do not equate a successful file write with acceptable separation quality.

---

## 19. Model version policy

Never overwrite provenance.

Changing:

- engine;
- model;
- model weights;
- inference options that materially alter output;

must create a distinct package identity or clearly new package revision.

A MediaHub user should be able to determine exactly which generator produced a package.

---

# PART VII — STORAGE

## 20. Stem Library

StemLab should support one or more output roots eventually, but start with one configured default library.

Example:

```text
D:/ViiB Stems/
    Human-9b83a2c148d1.viibstems/
    Another Track-18ea5f....viibstems/
```

Future modes:

- central library
- adjacent-to-source package
- portable playlist preparation directory

---

## 21. Disk budgeting

Six uncompressed stems can be much larger than the source.

Before batch generation, estimate required storage.

Future desktop behavior:

- show estimated output size;
- warn before exceeding free-space threshold;
- expose total Stem Library size;
- support cleanup by last access / age / playlist membership;
- never silently delete user-exported packages.

---

# PART VIII — MEDIAHUB INTEROPERABILITY

## 22. Contract tests

Eventually maintain fixtures that both repos consume.

Recommended approach:

```text
fixtures/
    package-v1-valid/
    package-v1-bad-checksum/
    package-v1-missing-stem/
    package-v1-stale-source/
    package-v1-path-traversal/
```

StemLab validates what it writes.

MediaHub independently validates what it reads.

The projects should never rely on shared in-process code for the validator because independent implementations catch contract ambiguity.

---

## 23. Optional application launch integration

Future MediaHub command:

```text
Generate Stems
```

Possible integration:

```text
viib-stemlab generate "<track>" --output "<configured-library>"
```

or a desktop deep link.

This is convenience only. MediaHub package discovery must remain filesystem-based.

---

# PART IX — SECURITY

## 24. Untrusted paths

Treat package manifests as untrusted input.

Reject:

- absolute stem paths;
- `..` traversal;
- symlink escapes where validation can detect them;
- duplicate canonical stem keys;
- unsupported codecs;
- unreasonable declared sizes/frame counts.

Never let a package cause validation or cleanup code to access arbitrary filesystem paths.

---

## 25. Model downloads

Model downloads must eventually be:

- HTTPS;
- versioned;
- checksum-verified when upstream metadata permits;
- stored outside package output;
- explicit in diagnostics.

Do not execute downloaded scripts or arbitrary package code as part of model loading.

---

# PART X — TESTING AND CI

## 26. Fast CI

Default CI must **not** need to download PyTorch or model weights.

The base test suite should cover:

- hashing;
- package naming;
- manifest serialization;
- schema semantics;
- path safety;
- WAV geometry;
- checksums;
- package validation;
- atomic finalization with a fake engine;
- CLI parsing.

Run this on:

- Windows
- macOS
- Linux

---

## 27. Heavy integration CI

Heavy/model integration should be separate from ordinary PR CI.

Available/manual heavy jobs:

- manual `Demucs Smoke` workflow with CPU `htdemucs_6s` — first real end-to-end run passed on 2026-09-24; durable evidence is recorded in `docs/PHASE2_DEMUCS_SMOKE.md`.

Possible future jobs:

- self-hosted NVIDIA runner;
- Apple Silicon runner;
- model-output fixture generation.

Do not make every code change download hundreds of megabytes of ML dependencies.

---

# PART XI — REPOSITORY STRUCTURE

## 28. Initial scaffold

```text
ViiB-StemLab/
    ROADMAP.md
    README.md
    pyproject.toml
    .gitignore

    docs/
        PHASE2_DEMUCS_SMOKE.md
        VIIB_STEM_PACKAGE_V1.md
        viib-stem-package-v1.schema.json

    fixtures/
        package-v1-valid.viibstems/
        package-v1-bad-checksum.viibstems/
        package-v1-missing-stem.viibstems/
        package-v1-path-traversal.viibstems/
        package-v1-bad-geometry.viibstems/
        package-v1-stale-source.viibstems/

    src/
        viib_stemlab/
            __init__.py
            __main__.py
            cli.py
            constants.py
            hashing.py
            manifest.py
            package.py
            validation.py

            engines/
                __init__.py
                base.py
                demucs.py

            services/
                __init__.py
                generate.py

    tests/
        test_cli.py
        test_conformance.py
        test_demucs_engine.py
        test_generate.py
        test_manifest.py
        test_package.py

    .github/
        workflows/
            ci.yml
            demucs-smoke.yml
```

Desktop/Tauri files should be added when Phase 4 begins instead of committing generated UI boilerplate before the application boundary is proven.

---

# PART XII — IMPLEMENTATION PHASES

## Phase 0 — Repository foundation

**Status: COMPLETE — 2026-09-24**

**Goal:** establish a tested core with no model download requirement.

Deliver:

- roadmap;
- README;
- Python package scaffold;
- CLI;
- engine protocol;
- manifest types;
- hashing;
- WAV metadata reader;
- package validator;
- CI matrix;
- deterministic synthetic tests.

Exit:

- `python -m viib_stemlab doctor` works without Demucs;
- package tests pass on Windows/macOS/Linux;
- repository can be installed in editable mode;
- no heavyweight model dependency is required for normal CI.

---

## Phase 1 — Package v1 freeze

**Status: STEMLAB SIDE COMPLETE; MEDIAHUB INDEPENDENT CONFORMANCE PENDING**

StemLab now has the draft specification, machine-readable JSON Schema, strict runtime validator, path-security coverage, and deterministic valid/invalid conformance fixtures. The remaining freeze gate is independent consumption of the same fixtures by ViiB MediaHub. Until that cross-repository check is complete, schema version 1 remains explicitly marked as a draft rather than frozen.

Deliver:

- formal package specification;
- per-stem checksum/size/frame fields;
- source hash;
- generator/model provenance;
- schema compatibility rules;
- path-security tests;
- valid/invalid fixture packages;
- review against MediaHub consumer implementation.

Exit:

- package v1 is frozen;
- MediaHub can independently parse/validate generated fixtures;
- no unresolved ambiguity about frame counts, codecs, hash semantics, or path rules.

---

## Phase 2 — Demucs MVP

**Status: STEMLAB IMPLEMENTATION COMPLETE — 2026-09-24; INDEPENDENT MEDIAHUB EXIT GATE PENDING**

The optional Demucs provider, detailed Torch/device capability detection, synchronous `generate` command, canonical six-stem collection, package writer, and atomic finalization path are implemented.

A real `htdemucs_6s` CPU smoke run completed successfully on 2026-09-24 (GitHub Actions run `36004541545`). It used Demucs 4.0.1 with PyTorch 2.6.0, generated six aligned 44.1 kHz stereo stems for a deterministic 3-second source, built `smoke-d95650ec6f83.viibstems`, and passed StemLab source/hash/geometry validation. The durable record is in `docs/PHASE2_DEMUCS_SMOKE.md`.

Fast CI also verifies that a geometry failure never promotes a partial package and that a failed overwrite promotion restores the prior valid package and removes temporary state.

The remaining exit gate is deliberately cross-repository: ViiB MediaHub must independently consume/validate the package contract.

Deliver:

- optional Demucs runtime;
- `htdemucs_6s`;
- CPU path;
- CUDA detection;
- MPS detection;
- `generate` CLI command;
- collection of six canonical outputs;
- complete package writer;
- atomic finalization.

Exit:

- one local track generates a valid ViiB Stem Package;
- package passes independent validation;
- failure never leaves a finalized partial package.

---

## Phase 3 — Robust generation

**Status: IN PROGRESS — CLI cancellation hardening started 2026-09-24**

Phase 2 established subprocess isolation at the single-generation level, atomic package promotion, overwrite rollback, and basic progress reporting. Phase 3 now also guarantees that a Ctrl+C interrupt terminates the owned Demucs subprocess and exits cleanly. The remaining work turns those primitives into production-grade programmatic job control and recovery.

Deliver:

- structured progress;
- generalized cancellation (CLI Ctrl+C cleanup implemented; queue/worker cancellation token pending);
- worker isolation;
- retry policy;
- explicit GPU-to-CPU fallback policy;
- detailed logs;
- disk-space preflight;
- duplicate/package-exists behavior;
- overwrite safety;
- model cache management.

Exit:

- cancellations release resources and clean temp data;
- CUDA/MPS failures have actionable diagnostics;
- repeated successful jobs do not leak memory/processes.

---

## Phase 4 — Queue and desktop shell

Deliver:

- durable queue;
- drag/drop;
- Add Files / Add Folder;
- batch preparation;
- settings;
- queue progress;
- cancel/retry;
- completed package library;
- desktop installer strategy.

Exit:

- user can prepare an entire DJ folder without CLI use;
- restart preserves queue state safely;
- no incomplete package is presented as complete.

---

## Phase 5 — Preview and quality tools

Deliver:

- synchronized six-lane preview;
- mute/solo/levels;
- original-versus-stem mix audition;
- waveform overview;
- package validation UI;
- model/device provenance display.

Exit:

- preview remains sample-aligned;
- UI does not alter finalized package audio.

---

## Phase 6 — Packaging and releases

Deliver:

- Windows self-contained runtime strategy;
- Apple Silicon runtime;
- macOS Intel decision based on supported Torch stack;
- Linux distribution strategy;
- model first-run setup;
- third-party notices;
- signed release artifacts where possible;
- automatic update strategy if desired.

Exit:

- end users do not need to install Python manually;
- runtime/model errors have recovery instructions;
- license/notice inventory is complete.

---

## Phase 7 — MediaHub handoff

Deliver:

- optional CLI/deep-link invocation from ViiB MediaHub;
- selected track handoff;
- playlist/batch handoff;
- post-completion package rescan hint;
- shared conformance fixtures.

Exit:

- MediaHub can request preparation without depending on StemLab at playback time.

---

## Phase 8 — Advanced engines and formats

Evaluate:

- FLAC package output;
- newer separation models;
- model quality profiles;
- ONNX provider;
- alternative stem layouts;
- GPU-specific optimized runtime;
- package migration tooling.

Any new engine must continue to emit a package compatible with the stable MediaHub contract.

---

# PART XIII — FIRST IMPLEMENTATION SLICES

## 29. Immediate commit sequence

After this roadmap:

### Scaffold commit — COMPLETE

- Python project
- CLI
- manifest/package modules
- engine interface
- Demucs optional provider
- tests
- CI
- README
- package spec draft

### Conformance contract — STEMLAB SIDE COMPLETE

- synthetic ViiB Stem Package fixtures
- stricter manifest validation
- JSON Schema
- cross-platform binary fixture handling
- external six-stem package builder

### Remaining shared Phase 1/2 gate

- MediaHub independent contract review and conformance-fixture validation
- MediaHub validation of a real StemLab-generated package before schema v1 is frozen

### Demucs MVP — STEMLAB SIDE COMPLETE

- real Demucs `htdemucs_6s` CPU generation
- first real six-stem package
- runtime/device diagnostics
- atomic rollback failure coverage
- durable smoke record

### Next

- complete MediaHub independent package validation
- continue structured progress, programmatic cancellation, and worker hardening

Do not start the desktop GUI before a real generated package has successfully round-tripped through MediaHub validation.

---

# PART XIV — DEFINITION OF DONE FOR 1.0

ViiB-StemLab 1.0 is ready when:

- a user can install it without manually provisioning Python;
- local tracks can be queued in batches;
- `htdemucs_6s` can run on supported CPU/CUDA/MPS targets;
- device choice and fallback are transparent;
- jobs can be cancelled safely;
- failed jobs never produce valid-looking packages;
- packages are atomically finalized;
- ViiB Stem Package v1 is stable;
- checksums and source hashes are verified;
- six canonical stems remain sample-aligned;
- MediaHub consumes packages without StemLab running;
- disk usage and output location are controllable;
- logs are sufficient to diagnose model/runtime failures;
- license and third-party notices are complete;
- Windows, macOS, and Linux support are documented with honest limitations.

---

# 30. Near-term priority

The priority order is:

1. **Freeze the ViiB Stem Package contract**
2. **Build a small, well-tested Python core**
3. **Generate one valid six-stem package with Demucs**
4. **Prove MediaHub can consume it**
5. **Harden cancellation, validation, and storage**
6. **Add batch queue**
7. **Add polished desktop UI**
8. **Package self-contained releases**
9. **Optimize models/runtime only after correctness is established**

The project should resist the temptation to become a full DAW or DJ player. Its most valuable output is a trustworthy, portable, versioned stem package that can be generated before a set and consumed reliably by ViiB MediaHub during performance.
