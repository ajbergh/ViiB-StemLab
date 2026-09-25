from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from conftest import FakeEngine

from viib_stemlab.errors import InsufficientDiskSpaceError
from viib_stemlab.preflight import (
    DiskSpaceEstimate,
    check_disk_space,
    estimate_required_disk_space,
    estimate_source_duration,
)
from viib_stemlab.services.generate import generate_package


def test_estimate_source_duration_wav(tmp_path: Path) -> None:
    from conftest import write_test_wav

    wav_path = tmp_path / "test.wav"
    # 44100 frames at 44100 Hz = 1.0 second
    write_test_wav(wav_path, frames=44100, sample_rate=44100)
    duration = estimate_source_duration(wav_path)
    assert pytest.approx(duration, 0.01) == 1.0


def test_estimate_required_disk_space(tmp_path: Path) -> None:
    from conftest import write_test_wav

    wav_path = tmp_path / "test.wav"
    write_test_wav(wav_path, frames=44100, sample_rate=44100)  # 1.0s

    est = estimate_required_disk_space(
        wav_path,
        stem_count=6,
        sample_rate=44100,
        channels=2,
        bytes_per_sample=2,
        headroom_bytes=10 * 1024 * 1024,  # 10 MB
    )
    # 1s * 44100 * 2 * 2 = 176,400 bytes per stem
    # 6 stems = 1,058,400 bytes
    assert est.estimated_stem_bytes == 1058400
    assert est.estimated_work_bytes == 1058400
    assert est.estimated_staging_bytes == 1058400
    assert est.headroom_bytes == 10 * 1024 * 1024
    assert est.required_output_bytes == 1058400 + 10 * 1024 * 1024


def test_check_disk_space_passes_when_ample_space(monkeypatch, tmp_path: Path) -> None:
    # Mock disk_usage to return 10 GB free
    fake_usage = MagicMock()
    fake_usage.free = 10 * 1024 * 1024 * 1024
    monkeypatch.setattr("shutil.disk_usage", lambda path: fake_usage)

    est = DiskSpaceEstimate(
        source_duration_seconds=180.0,
        estimated_stem_bytes=200 * 1024 * 1024,
        estimated_work_bytes=200 * 1024 * 1024,
        estimated_staging_bytes=200 * 1024 * 1024,
        headroom_bytes=50 * 1024 * 1024,
        required_output_bytes=250 * 1024 * 1024,
        required_temp_bytes=250 * 1024 * 1024,
        total_peak_bytes=450 * 1024 * 1024,
    )
    # Should not raise
    check_disk_space(output_root=tmp_path, estimate=est)


def test_check_disk_space_fails_when_insufficient_space(monkeypatch, tmp_path: Path) -> None:
    # Mock disk_usage to return only 5 MB free
    fake_usage = MagicMock()
    fake_usage.free = 5 * 1024 * 1024
    monkeypatch.setattr("shutil.disk_usage", lambda path: fake_usage)

    est = DiskSpaceEstimate(
        source_duration_seconds=180.0,
        estimated_stem_bytes=200 * 1024 * 1024,
        estimated_work_bytes=200 * 1024 * 1024,
        estimated_staging_bytes=200 * 1024 * 1024,
        headroom_bytes=50 * 1024 * 1024,
        required_output_bytes=250 * 1024 * 1024,
        required_temp_bytes=250 * 1024 * 1024,
        total_peak_bytes=450 * 1024 * 1024,
    )

    with pytest.raises(InsufficientDiskSpaceError) as exc_info:
        check_disk_space(output_root=tmp_path, estimate=est)

    assert exc_info.value.code == "disk_full"
    assert "Insufficient disk space" in exc_info.value.message
    assert exc_info.value.details["available_bytes"] == 5 * 1024 * 1024


def test_generate_package_aborts_on_preflight_disk_shortage(
    monkeypatch,
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    fake_usage = MagicMock()
    fake_usage.free = 1024  # 1 KB free
    monkeypatch.setattr("shutil.disk_usage", lambda path: fake_usage)

    engine = FakeEngine(stem_files)

    with pytest.raises(InsufficientDiskSpaceError):
        generate_package(
            source=source_file,
            output_root=tmp_path / "library",
            engine=engine,
            skip_preflight=False,
        )


def test_generate_package_allows_skip_preflight(
    monkeypatch,
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    fake_usage = MagicMock()
    fake_usage.free = 1024  # 1 KB free, would fail preflight
    monkeypatch.setattr("shutil.disk_usage", lambda path: fake_usage)

    engine = FakeEngine(stem_files)

    # With skip_preflight=True, it succeeds regardless
    package = generate_package(
        source=source_file,
        output_root=tmp_path / "library",
        engine=engine,
        skip_preflight=True,
    )
    assert package.exists()
