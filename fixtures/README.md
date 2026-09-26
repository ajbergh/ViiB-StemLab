# ViiB Stem Package v1 conformance fixtures

These fixtures are intentionally tiny and deterministic. They exist so ViiB-StemLab and
ViiB MediaHub can implement their package validators independently against the same inputs.

Contract: [../docs/VIIB_STEM_PACKAGE_V1.md](../docs/VIIB_STEM_PACKAGE_V1.md)  
Machine-readable schema: [../docs/viib-stem-package-v1.schema.json](../docs/viib-stem-package-v1.schema.json)

- `package-v1-valid.viibstems` — valid six-stem WAV package.
- `package-v1-bad-checksum.viibstems` — vocals checksum is intentionally wrong.
- `package-v1-missing-stem.viibstems` — required `other` stem is absent.
- `package-v1-path-traversal.viibstems` — vocals path attempts to escape the package.
- `package-v1-bad-geometry.viibstems` — piano contains one fewer audio frame.
- `package-v1-stale-source.viibstems` — source SHA-256 intentionally does not match
  `source/fixture-source.bin`.
- `package-v0-legacy.viibstems` — the valid package with its original StemLab 0.1.0
  manifest (`stems.*.file`, no `stemLayout`/`timing`). Input for `viib-stemlab package upgrade`.

The `package-v1-*` manifests follow the MediaHub v1 contract; MediaHub's validator accepts
`package-v1-valid`.

The WAV payloads are 16-bit PCM, stereo, 44.1 kHz, and only a few dozen frames long.
They are not model-quality test audio and must not be used to evaluate separation quality.


## Expected validator behavior

| Fixture | Expected result |
|---|---|
| `package-v1-valid.viibstems` | Accept. |
| `package-v1-bad-checksum.viibstems` | Reject because the vocals SHA-256 is wrong. |
| `package-v1-missing-stem.viibstems` | Reject because `other` is required. |
| `package-v1-path-traversal.viibstems` | Reject because the vocals path escapes the package. |
| `package-v1-bad-geometry.viibstems` | Reject because piano has a mismatched frame count. |
| `package-v1-stale-source.viibstems` | Reject against `source/fixture-source.bin` because the source SHA-256 is stale. |
| `package-v0-legacy.viibstems` | Reject as v1 (StemLab 0.1.0 manifest); accept after `package upgrade`. |

StemLab runs these fixtures in normal CI. MediaHub should reproduce these accept/reject outcomes with an independent implementation.
