"""ViiB-StemLab core package."""

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

__version__ = "0.1.0"

__all__ = [
    "CancellationToken",
    "ChecksumMismatchError",
    "CudaOutOfMemoryError",
    "CudaUnavailableError",
    "DiskSpaceEstimate",
    "GenerationCancelledError",
    "InferenceFailedError",
    "InsufficientDiskSpaceError",
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
    "SourceNotFoundError",
    "SourceUnreadableError",
    "StemLabError",
    "UnsupportedInputFormatError",
    "WorkerCrashedError",
    "__version__",
    "check_disk_space",
    "estimate_required_disk_space",
]
