from __future__ import annotations

import json
from pathlib import Path

from viib_stemlab.queue.discovery import (
    discover_audio_files,
    find_existing_package_for_source,
    ingest_paths,
)
from viib_stemlab.queue.store import QueueStore


def test_discover_audio_files(tmp_path: Path) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()

    # Supported audio
    f1 = music_dir / "track1.wav"
    f2 = music_dir / "track2.FLAC"
    f3 = music_dir / "track3.mp3"
    f4 = music_dir / "track4.ogg"
    for f in (f1, f2, f3, f4):
        f.touch()

    # Unsupported or ignored
    (music_dir / "notes.txt").touch()
    (music_dir / "cover.jpg").touch()

    # Subdirectory
    sub = music_dir / "subfolder"
    sub.mkdir()
    f5 = sub / "track5.wav"
    f5.touch()

    # Hidden folder
    hidden = music_dir / ".hidden"
    hidden.mkdir()
    (hidden / "secret.wav").touch()

    # Package folder (should be skipped)
    pkg_dir = music_dir / "song-123456789012.viibstems"
    pkg_dir.mkdir()
    (pkg_dir / "vocals.wav").touch()

    # Non-recursive
    discovered_flat = discover_audio_files(music_dir, recursive=False)
    assert len(discovered_flat) == 4
    assert set(discovered_flat) == {f1.resolve(), f2.resolve(), f3.resolve(), f4.resolve()}

    # Recursive
    discovered_rec = discover_audio_files(music_dir, recursive=True)
    assert len(discovered_rec) == 5
    assert set(discovered_rec) == {
        f1.resolve(),
        f2.resolve(),
        f3.resolve(),
        f4.resolve(),
        f5.resolve(),
    }


def test_find_existing_package_for_source(tmp_path: Path) -> None:
    lib_dir = tmp_path / "ViiB Stems"
    lib_dir.mkdir()

    source = tmp_path / "Awesome Track.wav"
    source.touch()

    assert find_existing_package_for_source(source, lib_dir) is None

    # Create mock package
    pkg = lib_dir / "Awesome_Track-abcdef123456.viibstems"
    pkg.mkdir()
    manifest_data = {
        "schemaVersion": 1,
        "source": {
            "filename": "Awesome Track.wav",
            "sha256": "abcdef1234567890",
            "sizeBytes": 1000,
        },
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    found = find_existing_package_for_source(source, lib_dir)
    assert found == pkg


def test_ingest_paths_with_deduplication(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    lib_dir = tmp_path / "stems"
    lib_dir.mkdir()

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    t1 = music_dir / "song1.wav"
    t2 = music_dir / "song2.flac"
    t1.touch()
    t2.touch()

    # Ingest folder
    res1 = ingest_paths([music_dir], store=store, output_library=lib_dir)
    assert len(res1.added) == 2
    assert len(res1.skipped_duplicate_queue) == 0
    assert len(res1.skipped_existing_package) == 0

    # Ingest same folder again without overwrite
    res2 = ingest_paths([music_dir], store=store, output_library=lib_dir)
    assert len(res2.added) == 0
    assert len(res2.skipped_duplicate_queue) == 2

    # Ingest with overwrite=True
    res3 = ingest_paths([music_dir], store=store, output_library=lib_dir, overwrite=True)
    assert len(res3.added) == 2
    assert len(res3.skipped_duplicate_queue) == 0


def test_ingest_skips_existing_packages(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    lib_dir = tmp_path / "stems"
    lib_dir.mkdir()

    source = tmp_path / "Track A.wav"
    source.touch()

    # Pre-create package in library
    pkg = lib_dir / "Track_A-1234567890ab.viibstems"
    pkg.mkdir()
    (pkg / "manifest.json").write_text(
        json.dumps({"source": {"filename": "Track A.wav"}}), encoding="utf-8"
    )

    res = ingest_paths([source], store=store, output_library=lib_dir)
    assert len(res.added) == 0
    assert len(res.skipped_existing_package) == 1
    assert res.skipped_existing_package[0] == source.resolve()
