"""ViiB-StemLab core package."""

__version__ = "0.1.0"

from viib_stemlab.cancellation import CancellationToken
from viib_stemlab.errors import (
    ChecksumMismatchError,
    CudaOutOfMemoryError,
    CudaUnavailableError,
    GenerationCancelledError,
    InferenceFailedError,
    InsufficientDiskSpaceError,
    ModelDownloadError,
    ModelMissingError,
    MpsUnavailableError,
    OutputGeometryMismatchError,
    OutputMissingError,
    PackageExistsError,
    PackageValidationError,
    PermissionDeniedError,
    SourceNotFoundError,
    SourceUnreadableError,
    StemLabError,
    UnsupportedInputFormatError,
    WorkerCrashedError,
)
from viib_stemlab.models import ModelCacheManager
from viib_stemlab.preflight import (
    DiskSpaceEstimate,
    check_disk_space,
    estimate_required_disk_space,
)
from viib_stemlab.progress import ProgressEmitter, ProgressUpdate
from viib_stemlab.queue import (
    BatchIngestResult,
    JobRecord,
    JobStatus,
    QueueRunner,
    QueueStore,
    discover_audio_files,
    find_existing_package_for_source,
    get_default_queue_db_path,
    ingest_paths,
)

__all__ = [
    "BatchIngestResult",
    "CancellationToken",
    "ChecksumMismatchError",
    "CudaOutOfMemoryError",
    "CudaUnavailableError",
    "DiskSpaceEstimate",
    "GenerationCancelledError",
    "InferenceFailedError",
    "InsufficientDiskSpaceError",
    "JobRecord",
    "JobStatus",
    "ModelCacheManager",
    "ModelDownloadError",
    "ModelMissingError",
    "MpsUnavailableError",
    "OutputGeometryMismatchError",
    "OutputMissingError",
    "PackageExistsError",
    "PackageValidationError",
    "PermissionDeniedError",
    "ProgressEmitter",
    "ProgressUpdate",
    "QueueRunner",
    "QueueStore",
    "SourceNotFoundError",
    "SourceUnreadableError",
    "StemLabError",
    "UnsupportedInputFormatError",
    "WorkerCrashedError",
    "__version__",
    "check_disk_space",
    "discover_audio_files",
    "estimate_required_disk_space",
    "find_existing_package_for_source",
    "get_default_queue_db_path",
    "ingest_paths",
]
