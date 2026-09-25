from __future__ import annotations

from viib_stemlab.errors import (
    ChecksumMismatchError,
    CudaOutOfMemoryError,
    CudaUnavailableError,
    DemucsUnavailableError,
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
    classify_error,
    classify_process_failure,
)


def test_stemlab_error_formatting() -> None:
    err = CudaOutOfMemoryError(
        "Allocated 8GB, out of VRAM",
        details={"allocated_mb": 8192, "gpu": "RTX 3080"},
    )
    assert isinstance(err, StemLabError)
    assert err.code == "cuda_oom"
    assert "Allocated 8GB" in err.message
    assert "GPU ran out of VRAM" in err.diagnostic
    formatted = err.format_user_message()
    assert "[cuda_oom]" in formatted
    assert "Diagnostic:" in formatted
    d = err.to_dict()
    assert d["code"] == "cuda_oom"
    assert d["details"]["allocated_mb"] == 8192


def test_exception_inheritance_compatibility() -> None:
    # Ensure backward compatibility with standard library exception catches
    assert issubclass(SourceNotFoundError, FileNotFoundError)
    assert issubclass(SourceUnreadableError, PermissionError)
    assert issubclass(PackageExistsError, FileExistsError)
    assert issubclass(PermissionDeniedError, PermissionError)
    assert issubclass(UnsupportedInputFormatError, ValueError)
    assert issubclass(InsufficientDiskSpaceError, OSError)
    assert issubclass(CudaUnavailableError, DemucsUnavailableError)
    assert issubclass(MpsUnavailableError, DemucsUnavailableError)
    assert issubclass(ModelMissingError, RuntimeError)
    assert issubclass(ChecksumMismatchError, ValueError)
    assert issubclass(OutputGeometryMismatchError, PackageValidationError)
    assert issubclass(PackageValidationError, ValueError)
    assert issubclass(OutputMissingError, RuntimeError)
    assert issubclass(OutputMissingError, ValueError)


def test_classify_process_failure_cuda_oom() -> None:
    tail = [
        "Demucs separation started...",
        "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 512.00 MiB",
    ]
    err = classify_process_failure(1, tail, "cuda")
    assert isinstance(err, CudaOutOfMemoryError)
    assert err.code == "cuda_oom"
    assert err.details["device"] == "cuda"


def test_classify_process_failure_disk_full() -> None:
    tail = [
        "Writing stems to disk...",
        "OSError: [Errno 28] No space left on device",
    ]
    err = classify_process_failure(1, tail, "cpu")
    assert isinstance(err, InsufficientDiskSpaceError)
    assert err.code == "disk_full"


def test_classify_process_failure_model_download() -> None:
    tail = [
        "Downloading model...",
        "urllib.error.HTTPError: HTTP Error 403: Forbidden",
    ]
    err = classify_process_failure(1, tail, "cpu")
    assert isinstance(err, ModelDownloadError)
    assert err.code == "model_download_failed"


def test_classify_process_failure_cancellation() -> None:
    err = classify_process_failure(130, ["Process interrupted"], "cpu")
    assert isinstance(err, GenerationCancelledError)
    assert err.code == "cancelled"

    err_term = classify_process_failure(143, ["Terminated"], "cuda")
    assert isinstance(err_term, GenerationCancelledError)


def test_classify_process_failure_worker_crashed() -> None:
    # Access violation on Windows
    err = classify_process_failure(-1073741819, ["Crash"], "cuda")
    assert isinstance(err, WorkerCrashedError)
    assert err.code == "worker_crashed"

    # SIGSEGV (-11)
    err_segv = classify_process_failure(-11, ["Segmentation fault"], "cpu")
    assert isinstance(err_segv, WorkerCrashedError)


def test_classify_process_failure_generic() -> None:
    err = classify_process_failure(1, ["Syntax error in internal script"], "cpu")
    assert isinstance(err, InferenceFailedError)
    assert err.code == "inference_failed"


def test_classify_error_normalization() -> None:
    fnf = classify_error(FileNotFoundError("track.wav missing"))
    assert isinstance(fnf, SourceNotFoundError)
    assert fnf.code == "source_not_found"

    fe = classify_error(FileExistsError("output already exists"))
    assert isinstance(fe, PackageExistsError)
    assert fe.code == "package_exists"

    pe = classify_error(PermissionError("denied"))
    assert isinstance(pe, PermissionDeniedError)
    assert pe.code == "permission_denied"

    ki = classify_error(KeyboardInterrupt())
    assert isinstance(ki, GenerationCancelledError)
    assert ki.code == "cancelled"

    oom = classify_error(RuntimeError("CUDA out of memory in PyTorch"))
    assert isinstance(oom, CudaOutOfMemoryError)

    disk = classify_error(OSError("[Errno 28] No space left on device"))
    assert isinstance(disk, InsufficientDiskSpaceError)
