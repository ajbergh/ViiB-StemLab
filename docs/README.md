# ViiB-StemLab documentation

This directory contains the durable technical documentation for ViiB-StemLab. The repository root [README](../README.md) is the quick-start entry point and [ROADMAP](../ROADMAP.md) is the implementation source of truth.

## Current project state

As of 2026-09-24:

- Phase 0 repository foundation is complete.
- The StemLab side of Phase 1 package-contract work is complete; independent MediaHub conformance remains before v1 is frozen.
- The StemLab side of Phase 2 Demucs MVP is complete.
- A real Demucs 4.0.1 `htdemucs_6s` CPU run generated and validated a six-stem `.viibstems` package.
- Phase 3 production hardening has not started beyond prerequisite safety primitives already established in Phase 2.

## Documents

| Document | Purpose |
|---|---|
| [VIIB_STEM_PACKAGE_V1.md](VIIB_STEM_PACKAGE_V1.md) | Human-readable filesystem and manifest contract between StemLab and consumers such as MediaHub. |
| [viib-stem-package-v1.schema.json](viib-stem-package-v1.schema.json) | Machine-readable JSON Schema for the v1 manifest. |
| [PHASE2_DEMUCS_SMOKE.md](PHASE2_DEMUCS_SMOKE.md) | Durable evidence from the first real `htdemucs_6s` end-to-end generation run. |
| [../fixtures/README.md](../fixtures/README.md) | Expected results for the shared positive/negative package conformance fixtures. |
| [../ROADMAP.md](../ROADMAP.md) | Architecture, implementation phases, exit gates, and next work. |

## Contract status

ViiB Stem Package schema version 1 is implemented by StemLab but still marked **draft**. The freeze criterion is independent validation by ViiB MediaHub against the shared fixtures and a real StemLab-generated package.

The integration rule remains:

> **StemLab owns generation. MediaHub owns performance.**

MediaHub must be able to consume completed packages without StemLab, Python, PyTorch, Demucs, or a GPU running during DJ playback.
