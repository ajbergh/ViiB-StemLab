from viib_stemlab.constants import CANONICAL_STEMS
from viib_stemlab.manifest import (
    AudioInfo,
    GeneratorInfo,
    ModelInfo,
    SourceInfo,
    StemFileInfo,
    StemManifest,
)


def test_manifest_round_trip() -> None:
    stems = {
        name: StemFileInfo(file=f"{name}.wav", sha256="a" * 64, sizeBytes=100, frames=10)
        for name in CANONICAL_STEMS
    }
    manifest = StemManifest(
        schemaVersion=1,
        packageId="track-abc",
        createdAt="2026-09-24T00:00:00Z",
        source=SourceInfo(filename="track.flac", sha256="b" * 64, sizeBytes=123),
        generator=GeneratorInfo(name="ViiB-StemLab", version="0.1.0"),
        model=ModelInfo(engine="fake", name="fake6", version="1", device="cpu"),
        audio=AudioInfo(
            codec="wav",
            sampleRate=44100,
            channels=2,
            frames=10,
            durationSeconds=10 / 44100,
        ),
        stems=stems,
    )

    restored = StemManifest.from_json(manifest.to_json())
    assert restored == manifest
    assert restored.structural_errors() == []


def test_manifest_requires_all_canonical_stems() -> None:
    manifest = StemManifest(
        schemaVersion=1,
        packageId="track-abc",
        createdAt="2026-09-24T00:00:00Z",
        source=SourceInfo(filename="track.wav", sha256="b" * 64, sizeBytes=123),
        generator=GeneratorInfo(name="ViiB-StemLab", version="0.1.0"),
        model=ModelInfo(engine="fake", name="fake6", version="1", device="cpu"),
        audio=AudioInfo(
            codec="wav",
            sampleRate=44100,
            channels=2,
            frames=10,
            durationSeconds=10 / 44100,
        ),
        stems={},
    )

    assert any("missing canonical stems" in error for error in manifest.structural_errors())
