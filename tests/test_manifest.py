from viib_stemlab.constants import CANONICAL_STEMS
from viib_stemlab.manifest import (
    AudioInfo,
    GeneratorInfo,
    ModelInfo,
    SourceInfo,
    StemFileInfo,
    StemManifest,
    TimingInfo,
    is_legacy_manifest,
    upgrade_legacy_manifest,
)

FRAMES = 441


def _stem(name: str, **overrides) -> StemFileInfo:
    values = {
        "path": f"{name}.wav",
        "sha256": "a" * 64,
        "sizeBytes": 100,
        "sampleRate": 44100,
        "channels": 2,
        "frames": FRAMES,
        "encoding": "pcm_s16le",
    }
    values.update(overrides)
    return StemFileInfo(**values)


def _manifest(**overrides) -> StemManifest:
    values = {
        "schemaVersion": 1,
        "packageId": "track-abc",
        "createdAt": "2026-09-24T00:00:00Z",
        "source": SourceInfo(filename="track.flac", sha256="b" * 64, duration=FRAMES / 44100, sizeBytes=123),
        "stemLayout": "six",
        "generator": GeneratorInfo(name="ViiB-StemLab", version="0.1.0"),
        "model": ModelInfo(name="fake6", version="1", engine="fake", device="cpu"),
        "audio": AudioInfo(sampleRate=44100, channels=2, frames=FRAMES),
        "timing": TimingInfo(),
        "stems": {name: _stem(name) for name in CANONICAL_STEMS},
    }
    values.update(overrides)
    return StemManifest(**values)


def test_manifest_round_trip() -> None:
    manifest = _manifest()
    restored = StemManifest.from_json(manifest.to_json())
    assert restored == manifest
    assert restored.structural_errors() == []


def test_written_manifest_contains_every_mediahub_required_field() -> None:
    # Mirrors requireManifestFields in MediaHub backend/internal/stems/manifest.go.
    data = _manifest().to_dict()
    for key in ("schemaVersion", "source", "stemLayout", "generator", "model", "audio", "timing", "stems"):
        assert key in data, key
    assert {"filename", "sha256", "duration"} <= set(data["source"])
    assert {"name", "version"} <= set(data["generator"])
    assert {"name", "version"} <= set(data["model"])
    assert {"sampleRate", "channels", "frames"} <= set(data["audio"])
    assert {"decoderDelayFrames", "startTrimFrames"} <= set(data["timing"])
    for stem in data["stems"].values():
        assert {"path", "sha256", "sizeBytes", "sampleRate", "channels", "frames", "encoding"} <= set(stem)


def test_manifest_requires_all_canonical_stems() -> None:
    manifest = _manifest(stems={})
    assert any("missing canonical stems" in error for error in manifest.structural_errors())


def test_four_stem_layout_is_accepted() -> None:
    four = ("vocals", "drums", "bass", "other")
    manifest = _manifest(stemLayout="four", stems={name: _stem(name) for name in four})
    assert manifest.structural_errors() == []


def test_layout_must_match_stem_keys() -> None:
    manifest = _manifest(stemLayout="four")
    assert any("unknown stem entries: guitar, piano" in error for error in manifest.structural_errors())


def test_duration_must_agree_with_frames() -> None:
    manifest = _manifest(source=SourceInfo(filename="track.flac", sha256="b" * 64, duration=1.0))
    assert "source.duration does not match audio.frames / audio.sampleRate" in manifest.structural_errors()


def test_stem_geometry_and_encoding_are_checked() -> None:
    stems = {name: _stem(name) for name in CANONICAL_STEMS}
    stems["piano"] = _stem("piano", frames=FRAMES - 1)
    stems["bass"] = _stem("bass", encoding="pcm_s24le")
    errors = _manifest(stems=stems).structural_errors()
    assert "piano declared geometry differs from package audio geometry" in errors
    assert any(error.startswith("bass.encoding 'pcm_s24le' is not supported") for error in errors)


def test_missing_contract_field_points_legacy_manifests_to_upgrade() -> None:
    legacy = {
        "schemaVersion": 1,
        "source": {"filename": "a.ogg", "sha256": "b" * 64, "sizeBytes": 1},
        "generator": {"name": "ViiB-StemLab", "version": "0.1.0"},
        "model": {"engine": "demucs", "name": "htdemucs_6s", "version": "4.0.1", "device": "cuda"},
        "audio": {"codec": "wav", "sampleRate": 44100, "channels": 2, "frames": FRAMES, "durationSeconds": FRAMES / 44100},
        "stems": {name: {"file": f"{name}.wav", "sha256": "a" * 64, "sizeBytes": 100, "frames": FRAMES} for name in CANONICAL_STEMS},
    }
    assert is_legacy_manifest(legacy)
    try:
        StemManifest.from_dict(legacy)
    except ValueError as exc:
        assert "viib-stemlab package upgrade" in str(exc)
    else:  # pragma: no cover - the legacy manifest must not parse as v1
        raise AssertionError("legacy manifest parsed as v1")

    formats = {name: (44100, 2, FRAMES, "pcm_s16le") for name in CANONICAL_STEMS}
    upgraded = upgrade_legacy_manifest(legacy, formats)
    assert upgraded.stemLayout == "six"
    assert upgraded.stems["vocals"].path == "vocals.wav"
    assert upgraded.timing == TimingInfo(0, 0)
    assert upgraded.source.duration == FRAMES / 44100
    assert upgraded.model.device == "cuda"
    assert upgraded.structural_errors() == []
