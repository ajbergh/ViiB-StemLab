from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from viib_stemlab.constants import CANONICAL_STEMS
from viib_stemlab.errors import InsufficientDiskSpaceError
from viib_stemlab.validation import read_wav_info


@dataclass(frozen=True)
class DiskSpaceEstimate:
    source_duration_seconds: float
    estimated_stem_bytes: int
    estimated_work_bytes: int
    estimated_staging_bytes: int
    headroom_bytes: int
    required_output_bytes: int
    required_temp_bytes: int
    total_peak_bytes: int


def estimate_source_duration(source: Path) -> float:
    """Determine or estimate audio duration in seconds for a source file."""
    source = Path(source)
    suffix = source.suffix.lower()

    if suffix == ".wav":
        try:
            info = read_wav_info(source)
            if info.duration_seconds > 0:
                return info.duration_seconds
        except Exception:
            pass

    # Try ffprobe if available
    ffprobe_bin = which("ffprobe")
    if ffprobe_bin:
        try:
            cmd = [
                ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(source),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            val = float(result.stdout.strip())
            if val > 0:
                return val
        except Exception:
            pass

    # Heuristic fallback based on format and file size
    size_bytes = source.stat().st_size if source.is_file() else 0
    if suffix == ".flac":
        # FLAC is typically ~800 kbps (~100 KB/s)
        bytes_per_sec = 100_000.0
    elif suffix in (".mp3", ".ogg"):
        # MP3/OGG typical DJ quality is ~256-320 kbps (~32-40 KB/s)
        bytes_per_sec = 35_000.0
    else:
        # Uncompressed or unknown
        bytes_per_sec = 176_400.0

    estimated = size_bytes / max(bytes_per_sec, 1.0)
    return max(30.0, estimated)


def estimate_required_disk_space(
    source: Path,
    *,
    stem_count: int = len(CANONICAL_STEMS),
    sample_rate: int = 44100,
    channels: int = 2,
    bytes_per_sample: int = 2,  # 16-bit PCM WAV
    headroom_bytes: int = 50 * 1024 * 1024,  # 50 MB buffer
) -> DiskSpaceEstimate:
    """Estimate required disk space for full generation including work and staging directories."""
    duration = estimate_source_duration(source)
    # Total uncompressed audio bytes for all canonical stems
    one_stem_bytes = int(duration * sample_rate * channels * bytes_per_sample)
    total_stems_bytes = one_stem_bytes * stem_count

    work_bytes = total_stems_bytes
    staging_bytes = total_stems_bytes

    required_output = staging_bytes + headroom_bytes
    required_temp = work_bytes + headroom_bytes
    total_peak = work_bytes + staging_bytes + headroom_bytes

    return DiskSpaceEstimate(
        source_duration_seconds=duration,
        estimated_stem_bytes=total_stems_bytes,
        estimated_work_bytes=work_bytes,
        estimated_staging_bytes=staging_bytes,
        headroom_bytes=headroom_bytes,
        required_output_bytes=required_output,
        required_temp_bytes=required_temp,
        total_peak_bytes=total_peak,
    )


def _get_existing_ancestor(path: Path) -> Path:
    target = path.resolve()
    while not target.exists() and target.parent != target:
        target = target.parent
    return target


def check_disk_space(
    output_root: Path,
    temp_dir: Path | None = None,
    estimate: DiskSpaceEstimate | None = None,
) -> None:
    """Preflight check that both output volume and temp volume have adequate free disk space."""
    if estimate is None:
        return

    output_root = Path(output_root)
    out_target = _get_existing_ancestor(output_root)
    out_usage = shutil.disk_usage(out_target)

    if out_usage.free < estimate.required_output_bytes:
        req_mb = estimate.required_output_bytes / (1024 * 1024)
        avail_mb = out_usage.free / (1024 * 1024)
        raise InsufficientDiskSpaceError(
            f"Insufficient disk space for output library at '{output_root}'. "
            f"Required: {req_mb:.1f} MB, Available: {avail_mb:.1f} MB",
            details={
                "target": str(out_target),
                "required_bytes": estimate.required_output_bytes,
                "available_bytes": out_usage.free,
            },
        )

    t_dir = Path(temp_dir or tempfile.gettempdir())
    temp_target = _get_existing_ancestor(t_dir)
    temp_usage = shutil.disk_usage(temp_target)

    if temp_usage.free < estimate.required_temp_bytes:
        req_mb = estimate.required_temp_bytes / (1024 * 1024)
        avail_mb = temp_usage.free / (1024 * 1024)
        raise InsufficientDiskSpaceError(
            f"Insufficient temporary disk space at '{t_dir}'. "
            f"Required: {req_mb:.1f} MB, Available: {avail_mb:.1f} MB",
            details={
                "target": str(temp_target),
                "required_bytes": estimate.required_temp_bytes,
                "available_bytes": temp_usage.free,
            },
        )
