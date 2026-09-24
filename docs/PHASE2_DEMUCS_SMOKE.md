# Phase 2 Demucs MVP smoke record

**Date:** 2026-09-24  
**Workflow:** `Demucs Smoke`  
**Run:** #1 / GitHub Actions run `36004541545`  
**Commit:** `de94a08c8eb23cdc44edeef60638333405da1789`  
**Result:** PASS

This record captures the first real end-to-end ViiB-StemLab generation using the production-candidate Demucs six-stem model rather than a fake engine or synthetic package builder.

## Runtime

The GitHub-hosted Ubuntu CPU runner reported:

- ViiB-StemLab `0.1.0`
- Python `3.12`
- Demucs `4.0.1`
- PyTorch `2.6.0+cu124`
- CUDA runtime packaged with PyTorch: `12.4`
- CUDA device available on runner: no
- MPS available: no
- selected device: `cpu`
- model: `htdemucs_6s`

This run proves the CPU execution path. CUDA and MPS detection are implemented and unit tested, but real accelerator execution remains a later platform-matrix validation item.

## Input

The workflow generated a deterministic stereo PCM WAV:

- sample rate: 44.1 kHz
- channels: 2
- duration: 3.0 seconds
- frames: 132,300
- source SHA-256: `d95650ec6f83a5d7206ed72ab9730eb2ef43bef82b29b98e961086a2dad811e8`

## Generated package

StemLab generated:

`smoke-d95650ec6f83.viibstems/`

The package contained:

- `manifest.json`
- `vocals.wav`
- `drums.wav`
- `bass.wav`
- `guitar.wav`
- `piano.wav`
- `other.wav`

Every stem was:

- WAV
- 44.1 kHz
- stereo
- 132,300 frames
- 3.0 seconds

The manifest recorded:

- generator: `ViiB-StemLab 0.1.0`
- engine: `demucs`
- model: `htdemucs_6s`
- model version: `4.0.1`
- actual device: `cpu`

Each canonical stem had its own SHA-256 checksum and the completed package passed:

`viib-stemlab package validate <package> --source smoke.wav`

with:

`VALID smoke-d95650ec6f83`

## Atomic-finalization coverage

In addition to the real model run, fast CI now verifies that:

- geometry mismatch fails before any completed `.viibstems` package is exposed;
- an overwrite promotion failure restores the previous valid package;
- temporary partial and backup directories are cleaned after the failure.

## Interpretation

This satisfies the StemLab-side Phase 2 requirement that a real `htdemucs_6s` CPU run can produce a complete, aligned, validated six-stem ViiB package.

The remaining Phase 2 exit gate is cross-repository independence: ViiB MediaHub must consume and independently validate the generated package/contract. That work is intentionally performed in the MediaHub repository.

This smoke test is an interoperability/correctness test, not a separation-quality benchmark and not a representative performance benchmark.
