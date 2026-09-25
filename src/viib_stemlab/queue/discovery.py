from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from viib_stemlab.constants import PACKAGE_SUFFIX, SUPPORTED_INPUT_EXTENSIONS
from viib_stemlab.package import safe_source_name
from viib_stemlab.queue.models import JobRecord, JobStatus
from viib_stemlab.queue.store import QueueStore


@dataclass
class BatchIngestResult:
    added: list[JobRecord] = field(default_factory=list)
    skipped_duplicate_queue: list[Path] = field(default_factory=list)
    skipped_existing_package: list[Path] = field(default_factory=list)
    invalid_files: list[Path] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return (
            len(self.added)
            + len(self.skipped_duplicate_queue)
            + len(self.skipped_existing_package)
            + len(self.invalid_files)
        )


def discover_audio_files(
    target: Path | str,
    *,
    recursive: bool = True,
) -> list[Path]:
    """Scan a file or directory for supported audio files (.wav, .flac, .mp3, .ogg)."""
    target_path = Path(target).resolve()
    if not target_path.exists():
        return []

    if target_path.is_file():
        if target_path.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS:
            return [target_path]
        return []

    results: list[Path] = []
    iterator = target_path.rglob("*") if recursive else target_path.glob("*")

    for item in iterator:
        if not item.is_file():
            continue
        # Skip hidden files and temporary directories
        if any(part.startswith(".") for part in item.parts):
            continue
        # Skip files within existing .viibstems packages
        if any(part.endswith(PACKAGE_SUFFIX) for part in item.parts[:-1]):
            continue
        if item.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS:
            results.append(item.resolve())

    return sorted(results)


def find_existing_package_for_source(
    source: Path,
    output_library: Path,
) -> Path | None:
    """Inspect output library to see if a valid completed package already exists for this source."""
    if not output_library.is_dir():
        return None

    safe_name = safe_source_name(source)
    prefixes = (f"{safe_name}-", f"{safe_name.replace(' ', '_')}-")

    for candidate in output_library.iterdir():
        if (
            candidate.is_dir()
            and candidate.name.endswith(PACKAGE_SUFFIX)
            and any(candidate.name.startswith(p) for p in prefixes)
        ):
            manifest_path = candidate / "manifest.json"
            if manifest_path.is_file():
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    # If the source filename matches, consider it an existing package
                    if data.get("source", {}).get("filename") == source.name:
                        return candidate
                except Exception:
                    pass
    return None


def ingest_paths(
    paths: Sequence[Path | str],
    *,
    store: QueueStore,
    output_library: Path | str,
    model: str = "htdemucs_6s",
    device: str = "auto",
    fallback_to_cpu: bool = True,
    overwrite: bool = False,
    recursive: bool = True,
) -> BatchIngestResult:
    """Discover audio files across paths and add non-duplicate tracks to the durable queue."""
    result = BatchIngestResult()
    out_lib = Path(output_library).resolve()

    # Collect all audio candidates
    candidates: list[Path] = []
    for p in paths:
        path_obj = Path(p).resolve()
        if not path_obj.exists():
            result.invalid_files.append(path_obj)
            continue
        if path_obj.is_file():
            if path_obj.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS:
                candidates.append(path_obj)
            else:
                result.invalid_files.append(path_obj)
        elif path_obj.is_dir():
            discovered = discover_audio_files(path_obj, recursive=recursive)
            candidates.extend(discovered)

    # Ingest candidates with deduplication
    for audio_file in candidates:
        # Check active queue duplicates
        existing_jobs = store.find_jobs_by_source(audio_file)
        has_active_or_complete = any(
            j.status
            in (
                JobStatus.QUEUED,
                JobStatus.PREPARING,
                JobStatus.SEPARATING,
                JobStatus.PACKAGING,
                JobStatus.VALIDATING,
                JobStatus.COMPLETE,
            )
            for j in existing_jobs
        )
        if has_active_or_complete and not overwrite:
            result.skipped_duplicate_queue.append(audio_file)
            continue

        # Check existing package on disk
        if not overwrite:
            existing_pkg = find_existing_package_for_source(audio_file, out_lib)
            if existing_pkg:
                result.skipped_existing_package.append(audio_file)
                continue

        # Add job to queue
        job = store.add_job(
            source_path=audio_file,
            output_library=out_lib,
            model=model,
            device=device,
            fallback_to_cpu=fallback_to_cpu,
            overwrite=overwrite,
        )
        result.added.append(job)

    return result
