# ViiB Stem Package v1 — Draft Contract

**Status:** Draft — StemLab implementation complete; independent MediaHub conformance pending  
**Schema version:** `1`  
**Canonical package suffix:** `.viibstems`

This document defines the filesystem contract between ViiB-StemLab and consumers such as ViiB MediaHub.

The package is intentionally independent from Python, PyTorch, Demucs, or any specific generator implementation.

Machine-readable schema: [viib-stem-package-v1.schema.json](viib-stem-package-v1.schema.json)  
Shared conformance fixtures: [../fixtures/](../fixtures/)  
First real generator evidence: [PHASE2_DEMUCS_SMOKE.md](PHASE2_DEMUCS_SMOKE.md)

The current StemLab implementation has produced and validated a real `htdemucs_6s` six-stem package. The contract remains labeled **draft** only because the independent MediaHub consumer gate has not yet been closed.

## 1. Directory layout

A v1 package is a directory:

```text
<safe-source-name>-<sha-prefix>.viibstems/
    manifest.json
    vocals.wav
    drums.wav
    bass.wav
    guitar.wav
    piano.wav
    other.wav
```

The six canonical v1 stem names are:

1. `vocals`
2. `drums`
3. `bass`
4. `guitar`
5. `piano`
6. `other`

All six are required in a finalized v1 package.

## 2. Source identity

The manifest stores a SHA-256 digest of the original source file.

The source hash is the authoritative MediaHub staleness check. Filename and path are not authoritative identities.

The package name uses the first 12 hexadecimal characters of the source SHA-256 only for human readability and collision resistance. Consumers must use the complete hash from the manifest when verifying source identity.

## 3. Draft manifest

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
    "durationSeconds": 355.2111337868
  },
  "stems": {
    "vocals": {
      "file": "vocals.wav",
      "sha256": "...",
      "sizeBytes": 62660000,
      "frames": 15664861
    },
    "drums": {
      "file": "drums.wav",
      "sha256": "...",
      "sizeBytes": 62660000,
      "frames": 15664861
    },
    "bass": {
      "file": "bass.wav",
      "sha256": "...",
      "sizeBytes": 62660000,
      "frames": 15664861
    },
    "guitar": {
      "file": "guitar.wav",
      "sha256": "...",
      "sizeBytes": 62660000,
      "frames": 15664861
    },
    "piano": {
      "file": "piano.wav",
      "sha256": "...",
      "sizeBytes": 62660000,
      "frames": 15664861
    },
    "other": {
      "file": "other.wav",
      "sha256": "...",
      "sizeBytes": 62660000,
      "frames": 15664861
    }
  }
}
```

## 4. Required fields

### Root

| Field | Type | Meaning |
|---|---|---|
| `schemaVersion` | integer | Package schema major version. Must be `1` for v1. |
| `packageId` | string | Human-readable package identifier. |
| `createdAt` | string | UTC RFC 3339 / ISO-8601 timestamp. |
| `source` | object | Original source identity. |
| `generator` | object | Generator application provenance. |
| `model` | object | Separation-engine provenance. |
| `audio` | object | Geometry common to every canonical stem. |
| `stems` | object | Exactly the required canonical stem entries for current draft v1. |

### Source

| Field | Type | Meaning |
|---|---|---|
| `filename` | string | Original source basename; informational only. |
| `sha256` | string | Lowercase 64-character SHA-256 digest. |
| `sizeBytes` | integer | Original source file size. |

### Generator

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Generator identity, normally `ViiB-StemLab`. |
| `version` | string | Generator version. |

### Model

| Field | Type | Meaning |
|---|---|---|
| `engine` | string | Inference provider, initially `demucs`. |
| `name` | string | Model name, initially `htdemucs_6s`. |
| `version` | string | Engine/model package version when available. |
| `device` | string | Actual compute device used, such as `cpu`, `cuda`, or `mps`. |

### Audio

| Field | Type | Meaning |
|---|---|---|
| `codec` | string | Package stem codec; initial v1 scaffold supports `wav`. |
| `sampleRate` | integer | Samples per second. |
| `channels` | integer | Channel count common to every stem. |
| `frames` | integer | Frame count common to every stem. |
| `durationSeconds` | number | `frames / sampleRate`. |

### Stem entry

| Field | Type | Meaning |
|---|---|---|
| `file` | string | Safe package-relative filename. |
| `sha256` | string | Lowercase SHA-256 of this stem file. |
| `sizeBytes` | integer | File byte count. |
| `frames` | integer | Audio frame count. |

## 5. Path safety

A stem `file` value must:

- be relative;
- remain within the package directory after canonical resolution;
- contain no `..` component;
- not be a Windows drive path;
- not be a UNC path;
- not resolve through a symlink outside the package.

Consumers must not concatenate manifest paths and trust the result without validation.

## 6. Audio geometry

For draft v1:

- all stems use the same codec;
- all stems use the same sample rate;
- all stems use the same channel count;
- all stems use the same frame count;
- `audio.frames` is the common frame count;
- `durationSeconds` is derived from frames/sample rate.

The current implementation requires exact frame equality, and the first real `htdemucs_6s` smoke package satisfied that requirement across all six stems. If future supported engines demonstrate a legitimate bounded tolerance is needed, that behavior must be specified before changing the contract.

## 7. Checksums

SHA-256 is computed over the complete file bytes.

Source and stem digests are lowercase hexadecimal strings.

A checksum mismatch invalidates the package.

## 8. Atomic finalization

A generator must not write directly into the final package path.

Required pattern:

```text
.<packageId>.partial-<uuid>/
        ...
             |
             | validate
             v
<packageId>.viibstems/
```

The staging directory should be on the same filesystem as the final output directory so final rename can be atomic.

A consumer may treat a `.viibstems` directory as a candidate package, but still must validate its manifest and files.

## 9. Overwrite behavior

Overwrite is explicit.

A safe implementation:

1. build and validate a new staging package;
2. rename the old final package to a temporary backup;
3. rename the new staging package into place;
4. remove the backup;
5. restore the backup if promotion fails.

A failed regeneration must not destroy the previously valid package.

## 10. Forward compatibility

Draft v1 rules:

- unknown `schemaVersion` => unsupported;
- unknown optional fields under a known schema may be ignored;
- required field meaning must never change without a schema-version change;
- consumers should preserve unknown fields if they ever rewrite manifests.

The schema is still a draft until the MediaHub consumer independently validates the shared conformance fixtures and a real StemLab-generated package.

## 11. Codec evolution

WAV is the scaffold codec because it avoids a transcode step after Demucs.

FLAC should be benchmarked before 1.0. If adopted:

- manifest `audio.codec` distinguishes WAV and FLAC;
- existing WAV packages remain valid;
- MediaHub must not infer codec only from file extension.

## 12. Conformance fixtures

The repository now contains deterministic conformance fixtures:

```text
fixtures/
    package-v1-valid.viibstems/
    package-v1-bad-checksum.viibstems/
    package-v1-missing-stem.viibstems/
    package-v1-bad-geometry.viibstems/
    package-v1-path-traversal.viibstems/
    package-v1-stale-source.viibstems/
    source/fixture-source.bin
```

Expected outcomes are documented in [../fixtures/README.md](../fixtures/README.md).

StemLab validates these fixtures in normal cross-platform CI. MediaHub should implement its validator independently against the same fixture semantics rather than importing StemLab validation code.

## 13. Current implementation evidence

As of 2026-09-24:

- StemLab package construction, hashing, path safety, geometry validation, overwrite rollback, and conformance tests pass on Windows, macOS, and Linux CI;
- a real Demucs 4.0.1 / `htdemucs_6s` CPU run generated a valid six-stem package;
- every generated stem in that smoke run was stereo, 44.1 kHz, and exactly 132,300 frames;
- the generated package passed source hash, stem hash, byte-size, and WAV geometry validation;
- independent MediaHub consumption remains the final freeze gate.

See [PHASE2_DEMUCS_SMOKE.md](PHASE2_DEMUCS_SMOKE.md) for the durable run record.
