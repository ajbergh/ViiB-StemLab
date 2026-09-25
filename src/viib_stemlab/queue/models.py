from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from viib_stemlab.constants import DEFAULT_MODEL


class JobStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    SEPARATING = "separating"
    PACKAGING = "packaging"
    VALIDATING = "validating"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobRecord:
    id: str
    source_path: str
    output_library: str
    source_hash: str | None = None
    model: str = DEFAULT_MODEL
    device: str = "auto"
    actual_device: str | None = None
    fallback_to_cpu: bool = True
    overwrite: bool = False
    status: JobStatus = JobStatus.QUEUED
    stage: str | None = None
    progress: float | None = None
    progress_message: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error_code: str | None = None
    diagnostic_message: str | None = None
    package_path: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self.status in (
            JobStatus.PREPARING,
            JobStatus.SEPARATING,
            JobStatus.PACKAGING,
            JobStatus.VALIDATING,
            JobStatus.FINALIZING,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobRecord:
        d = dict(data)
        if "status" in d and isinstance(d["status"], str):
            d["status"] = JobStatus(d["status"])
        if "fallback_to_cpu" in d:
            d["fallback_to_cpu"] = bool(d["fallback_to_cpu"])
        if "overwrite" in d:
            d["overwrite"] = bool(d["overwrite"])
        return cls(**d)
