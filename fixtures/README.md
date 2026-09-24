# ViiB Stem Package v1 conformance fixtures

These fixtures are intentionally tiny and deterministic. They exist so ViiB-StemLab and
ViiB MediaHub can implement their package validators independently against the same inputs.

- `package-v1-valid.viibstems` — valid six-stem WAV package.
- `package-v1-bad-checksum.viibstems` — vocals checksum is intentionally wrong.
- `package-v1-missing-stem.viibstems` — required `other` stem is absent.
- `package-v1-path-traversal.viibstems` — vocals path attempts to escape the package.
- `package-v1-bad-geometry.viibstems` — piano contains one fewer audio frame.
- `package-v1-stale-source.viibstems` — source SHA-256 intentionally does not match
  `source/fixture-source.bin`.

The WAV payloads are 16-bit PCM, stereo, 44.1 kHz, and only a few dozen frames long.
They are not model-quality test audio and must not be used to evaluate separation quality.
