# ViiB Stem Package v1

**Status:** Aligned with the ViiB MediaHub v1 consumer contract; MediaHub validates StemLab output (2026-09-25)  
**Schema version:** `1`  
**Canonical package suffix:** `.viibstems`

This document describes the filesystem contract between ViiB-StemLab and consumers such as ViiB MediaHub, from the producer's side.

**The consumer contract is authoritative.** It is `docs/VIIB_STEM_PACKAGE_V1.md` in ViiB MediaHub, implemented by `backend/internal/stems/manifest.go`. If this document and the MediaHub contract ever disagree, the MediaHub contract wins and this document is out of date.

The package is intentionally independent from Python, PyTorch, Demucs, or any specific generator implementation.

Machine-readable schema: [viib-stem-package-v1.schema.json](viib-stem-package-v1.schema.json)  
Shared conformance fixtures: [../fixtures/](../fixtures/)  
First real generator evidence: [PHASE2_DEMUCS_SMOKE.md](PHASE2_DEMUCS_SMOKE.md)

> **StemLab 0.1.0 packages** were written against an earlier draft of this document, which MediaHub never accepted. MediaHub rejects every such package with `manifest.stemLayout is required`. Convert them with `viib-stemlab package upgrade` (section 14). The stem audio is unchanged; only `manifest.json` is rewritten.

## 1. Directory layout

A package is a directory:

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

v1 defines two layouts. StemLab writes `six`.

| `stemLayout` | Stems (exactly) |
|---|---|
| `four` | `vocals`, `drums`, `bass`, `other` |
| `six` | `vocals`, `drums`, `bass`, `guitar`, `piano`, `other` |

Files not named by the manifest (for example `cover.jpg`) are ignored by readers.

## 2. Source identity

The manifest stores a SHA-256 digest of the complete original source file, including tags and embedded artwork. It is the authoritative identity MediaHub uses to attach a package to a library track. Filename and path are not identities.

MediaHub also accepts an optional `source.audioSha256` over canonical decoded PCM, so a package can survive tag edits. The algorithm is defined in the MediaHub contract. StemLab does not write it yet, so **retagging a source after generation makes its package stale in MediaHub**; regenerate the package, or re-run once StemLab writes `audioSha256`.

The package name uses the first 12 hexadecimal characters of the source SHA-256 only for readability. Consumers must use the complete hash.

## 3. Manifest

```json
{
  "schemaVersion": 1,
  "packageId": "Human-9b83a2c148d1",
  "createdAt": "2026-09-24T00:00:00Z",
  "source": {
    "filename": "Human.flac",
    "sha256": "9b83a2c148d1…",
    "duration": 355.2111337868,
    "sizeBytes": 123456789
  },
  "stemLayout": "six",
  "generator": { "name": "ViiB-StemLab", "version": "0.1.0" },
  "model": { "name": "htdemucs_6s", "version": "4.0.1", "engine": "demucs", "device": "cuda" },
  "audio": { "sampleRate": 44100, "channels": 2, "frames": 15664861 },
  "timing": { "decoderDelayFrames": 0, "startTrimFrames": 0 },
  "stems": {
    "vocals": { "path": "vocals.wav", "sha256": "…", "sizeBytes": 62660000, "sampleRate": 44100, "channels": 2, "frames": 15664861, "encoding": "pcm_s16le" },
    "drums":  { "path": "drums.wav",  "sha256": "…", "sizeBytes": 62660000, "sampleRate": 44100, "channels": 2, "frames": 15664861, "encoding": "pcm_s16le" },
    "bass":   { "path": "bass.wav",   "sha256": "…", "sizeBytes": 62660000, "sampleRate": 44100, "channels": 2, "frames": 15664861, "encoding": "pcm_s16le" },
    "guitar": { "path": "guitar.wav", "sha256": "…", "sizeBytes": 62660000, "sampleRate": 44100, "channels": 2, "frames": 15664861, "encoding": "pcm_s16le" },
    "piano":  { "path": "piano.wav",  "sha256": "…", "sizeBytes": 62660000, "sampleRate": 44100, "channels": 2, "frames": 15664861, "encoding": "pcm_s16le" },
    "other":  { "path": "other.wav",  "sha256": "…", "sizeBytes": 62660000, "sampleRate": 44100, "channels": 2, "frames": 15664861, "encoding": "pcm_s16le" }
  }
}
```

## 4. Fields

"Required" means required by the MediaHub contract. "Extension" fields are written by StemLab and ignored by v1 readers.

### Root

| Field | Requirement | Meaning |
|---|---|---|
| `schemaVersion` | required | Integer `1`. Readers reject any other value. |
| `requiredFeatures` | optional | Capabilities a reader must implement. StemLab writes none. |
| `source` | required | Source identity. |
| `stemLayout` | required | `four` or `six`, exactly matching the stem keys. |
| `generator` | required | Producer provenance. |
| `model` | required | Separation-model provenance. |
| `audio` | required | PCM geometry common to every stem. |
| `timing` | required | Producer-side timing compensation. |
| `stems` | required | Exactly the stems of `stemLayout`. |
| `packageId` | extension | Human-readable package identifier. |
| `createdAt` | extension | UTC RFC 3339 timestamp. |

### Source

| Field | Requirement | Meaning |
|---|---|---|
| `filename` | required | Source basename; display only, never resolved as a path. |
| `sha256` | required | 64-character hexadecimal SHA-256 of the complete source file (StemLab writes lowercase). |
| `duration` | required | Seconds; must equal `audio.frames / audio.sampleRate` within one frame plus 1 ms. |
| `audioSha256` | optional | Decoded-audio identity (see section 2). Not yet written by StemLab. |
| `sizeBytes` | extension | Source byte size, used by `viib-stemlab package validate --source`. |

### Generator and model

| Field | Requirement | Meaning |
|---|---|---|
| `generator.name`, `generator.version` | required | Normally `ViiB-StemLab` and the StemLab version. |
| `model.name`, `model.version` | required | For example `htdemucs_6s` and the engine package version. |
| `model.engine`, `model.device` | extension | Inference provider (for example `demucs`) and the compute device actually used. |

### Audio and timing

| Field | Requirement | Meaning |
|---|---|---|
| `audio.sampleRate` | required | Positive samples per second. |
| `audio.channels` | required | `1` or `2`. |
| `audio.frames` | required | Positive frame count common to every stem. |
| `timing.decoderDelayFrames` | required | Non-negative decoder delay compensated by the producer. |
| `timing.startTrimFrames` | required | Non-negative frames trimmed at the start by the producer. |

StemLab packages separator output as-is and writes `0` for both timing fields, meaning no compensation or trim was applied.

### Stem entry

| Field | Requirement | Meaning |
|---|---|---|
| `path` | required | Package-relative `/`-separated path to a `.wav`/`.wave` file (section 5). |
| `sha256` | required | SHA-256 of the complete stem file bytes. |
| `sizeBytes` | required | Positive file size in bytes. |
| `sampleRate`, `channels`, `frames` | required | Must equal `audio` and the file's WAV header and data length. |
| `encoding` | required | `pcm_s16le` (PCM 16-bit) or `float32le` (IEEE float 32-bit). |

## 5. Path safety

A stem `path` must:

- be relative and use `/` as the separator;
- contain no backslash, NUL, empty, `.` or `..` segment;
- not be a drive or UNC path;
- remain within the package directory after canonical resolution, including through symlinks;
- name a regular `.wav` or `.wave` file.

Consumers must not concatenate manifest paths and trust the result without validation.

## 6. Audio geometry and encoding

- Every stem has identical sample rate, channel count, frame count and encoding. There is no frame-count tolerance.
- Stems are WAV PCM16 or WAV IEEE float32, mono or stereo. Other WAV subtypes (for example 24-bit PCM) and other codecs are rejected. `WAVE_FORMAT_EXTENSIBLE` headers are classified by their SubFormat.
- Frame zero of each stem corresponds to frame zero of the canonical source decode after the declared `timing` compensation.

## 7. Checksums

SHA-256 is computed over the complete file bytes. Readers accept upper- or lowercase hex; StemLab writes lowercase. A checksum or size mismatch invalidates the package.

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

- Unknown `schemaVersion` means unsupported.
- Unknown optional fields under a known schema are ignored.
- A producer that needs a reader capability lists it in `requiredFeatures`; readers reject unknown required features.
- Required-field meaning never changes without a schema-version change.
- Consumers should preserve unknown fields if they ever rewrite manifests.

## 11. Codec evolution

WAV is the v1 codec because it avoids a transcode step after Demucs. FLAC is not accepted by MediaHub v1; enabling it requires the MediaHub contract and validator to change together, and existing WAV packages remain valid.

## 12. Conformance fixtures

```text
fixtures/
    package-v1-valid.viibstems/
    package-v1-bad-checksum.viibstems/
    package-v1-missing-stem.viibstems/
    package-v1-bad-geometry.viibstems/
    package-v1-path-traversal.viibstems/
    package-v1-stale-source.viibstems/
    package-v0-legacy.viibstems/      # StemLab 0.1.0 manifest, input for `package upgrade`
    source/fixture-source.bin
```

Expected outcomes are documented in [../fixtures/README.md](../fixtures/README.md). StemLab validates these fixtures in normal CI, and MediaHub's independent Go validator accepts `package-v1-valid`.

## 13. Implementation evidence

- 2026-09-24: StemLab package construction, hashing, path safety, geometry validation, overwrite rollback and conformance tests pass on Windows, macOS and Linux CI. A real Demucs 4.0.1 / `htdemucs_6s` run generated a valid six-stem package (see [PHASE2_DEMUCS_SMOKE.md](PHASE2_DEMUCS_SMOKE.md)).
- 2026-09-25: StemLab manifests were found not to match the MediaHub contract, and all StemLab 0.1.0 packages were rejected by MediaHub. StemLab now writes the contract fields. MediaHub's validator accepts a freshly built StemLab package, the `package-v1-valid` fixture, and real 0.1.0 packages after `package upgrade`.

## 14. Upgrading StemLab 0.1.0 packages

```text
viib-stemlab package upgrade <package-or-library-dir> [--dry-run] [--no-hashes] [--verbose]
```

For each `.viibstems` directory found (recursively), the command:

1. skips packages that are already v1;
2. reads each stem's WAV header for geometry and encoding, which 0.1.0 did not record;
3. keeps the original manifest as `manifest.v0.json` (never overwritten once present);
4. writes the v1 manifest atomically, carrying over all hashes, sizes and paths, with `stemLayout` from the stem keys, `source.duration` from `audio.durationSeconds`, and zero `timing`;
5. re-validates the package, including stem SHA-256 unless `--no-hashes` is given, and restores the original manifest if validation fails.

After upgrading, run a Stem Library scan in MediaHub to attach the packages to their tracks.
