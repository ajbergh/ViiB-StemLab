from __future__ import annotations

import re
from typing import Any


class StemLabError(Exception):
    """Base exception for all structured ViiB-StemLab errors."""

    code: str = "stemlab_error"
    diagnostic: str = ""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        diagnostic: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if diagnostic is not None:
            self.diagnostic = diagnostic
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "diagnostic": self.diagnostic,
            "details": self.details,
        }

    def format_user_message(self) -> str:
        lines = [f"[{self.code}] {self.message}"]
        if self.diagnostic:
            lines.append(f"Diagnostic: {self.diagnostic}")
        return "\n".join(lines)


class SourceNotFoundError(StemLabError, FileNotFoundError):
    code = "source_not_found"
    diagnostic = "Verify that the audio source file path exists and is spelled correctly."


class SourceUnreadableError(StemLabError, PermissionError):
    code = "source_unreadable"
    diagnostic = "Verify file read permissions and ensure the file is not corrupted or locked."


class UnsupportedInputFormatError(StemLabError, ValueError):
    code = "unsupported_input"
    diagnostic = "Convert your audio to a supported input format: .wav, .flac, .mp3, or .ogg."


class ModelMissingError(StemLabError, RuntimeError):
    code = "model_missing"
    diagnostic = (
        "Download model weights or ensure an internet connection is available for auto-download."
    )


class ModelDownloadError(StemLabError, RuntimeError):
    code = "model_download_failed"
    diagnostic = "Check internet connectivity, proxy settings, or configure an offline model cache directory."


class DemucsUnavailableError(StemLabError, RuntimeError):
    code = "demucs_unavailable"
    diagnostic = "Install Demucs with the 'demucs' extra and verify runtime requirements."


class CudaUnavailableError(DemucsUnavailableError):
    code = "cuda_unavailable"
    diagnostic = (
        "Verify NVIDIA GPU drivers and a CUDA-compatible PyTorch install, or run with --device cpu."
    )


class CudaOutOfMemoryError(StemLabError, RuntimeError):
    code = "cuda_oom"
    diagnostic = (
        "GPU ran out of VRAM. Run with --device cpu, enable --fallback-to-cpu, or free GPU memory."
    )


class MpsUnavailableError(DemucsUnavailableError):
    code = "mps_unavailable"
    diagnostic = "Apple Silicon MPS is unavailable. Run with --device cpu or check macOS version."


class InferenceFailedError(StemLabError, RuntimeError):
    code = "inference_failed"
    diagnostic = "Separation engine inference failed. Review output logs for details."


class WorkerCrashedError(StemLabError, RuntimeError):
    code = "worker_crashed"
    diagnostic = (
        "Separation worker process crashed unexpectedly. Check system memory and GPU stability."
    )


class GenerationCancelledError(StemLabError):
    code = "cancelled"
    diagnostic = "Generation job was cancelled. All temporary directories and partial outputs have been cleaned up."


class OutputMissingError(StemLabError, RuntimeError, ValueError):
    code = "output_missing"
    diagnostic = "Model completed without generating all canonical stems (vocals, drums, bass, guitar, piano, other)."


class PackageValidationError(StemLabError, ValueError):
    code = "package_validation_failed"
    diagnostic = "The stem package does not meet the ViiB Stem Package v1 specification."

    def __init__(
        self,
        errors: list[str] | str,
        *,
        code: str = "package_validation_failed",
        diagnostic: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(errors, list):
            self.errors = errors
            message = "; ".join(errors)
        else:
            self.errors = [errors]
            message = errors
        super().__init__(
            message,
            code=code,
            diagnostic=diagnostic or self.diagnostic,
            details=details or {"validation_errors": self.errors},
        )


class OutputGeometryMismatchError(PackageValidationError):
    code = "output_geometry_mismatch"
    diagnostic = (
        "Separated stems must have identical sample rates, channel counts, and frame counts."
    )

    def __init__(
        self,
        errors: list[str] | str,
        *,
        code: str = "output_geometry_mismatch",
        diagnostic: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(errors, code=code, diagnostic=diagnostic, details=details)


class ChecksumMismatchError(StemLabError, ValueError):
    code = "checksum_failed"
    diagnostic = "Computed stem checksum does not match manifest. The output file may be damaged."


class InsufficientDiskSpaceError(StemLabError, OSError):
    code = "disk_full"
    diagnostic = (
        "Free up storage space on the output and temporary drives before starting generation."
    )


class PermissionDeniedError(StemLabError, PermissionError):
    code = "permission_denied"
    diagnostic = (
        "Ensure you have write permissions to the output library and temporary directories."
    )


class PackageExistsError(StemLabError, FileExistsError):
    code = "package_exists"
    diagnostic = "Package already exists. Use --overwrite to replace the existing package."


_CUDA_OOM_PATTERNS = re.compile(
    r"(CUDA out of memory|torch\.cuda\.OutOfMemoryError|CUDA error: out of memory)",
    re.IGNORECASE,
)
_DISK_FULL_PATTERNS = re.compile(
    r"(No space left on device|\[Errno 28\]|disk full)",
    re.IGNORECASE,
)
_DOWNLOAD_PATTERNS = re.compile(
    r"(HTTPError|URLError|ConnectionError|Failed to download|get_model.*failed|urlopen error)",
    re.IGNORECASE,
)


def classify_process_failure(
    return_code: int,
    output_tail: list[str] | str,
    device: str,
) -> StemLabError:
    """Analyze a failed process return code and output text to classify the failure mode."""
    full_text = "\n".join(output_tail) if isinstance(output_tail, list) else output_tail

    # Check CUDA OOM
    if _CUDA_OOM_PATTERNS.search(full_text):
        return CudaOutOfMemoryError(
            f"CUDA out of memory while separating on device {device!r}",
            details={"device": device, "return_code": return_code, "output": full_text},
        )

    # Check disk full
    if _DISK_FULL_PATTERNS.search(full_text):
        return InsufficientDiskSpaceError(
            "Disk became full during separation process",
            details={"device": device, "return_code": return_code, "output": full_text},
        )

    # Check model download failure
    if _DOWNLOAD_PATTERNS.search(full_text):
        return ModelDownloadError(
            "Model download failed during separation setup",
            details={"device": device, "return_code": return_code, "output": full_text},
        )

    # Check cancellation exit codes (e.g., 130 = SIGINT, -2 = SIGINT on Unix, 143 / -15 = SIGTERM)
    if return_code in (130, -2, 143, -15):
        return GenerationCancelledError(
            "Separation process was terminated by cancellation signal",
            details={"return_code": return_code},
        )

    # Check abnormal crashes: negative exit code on Unix, or Windows fatal exceptions
    crash_codes = {-1073741819, 3221225477, -1073740791, 3221226505, -11, -6}
    if return_code < 0 or return_code in crash_codes:
        return WorkerCrashedError(
            f"Separation worker crashed abnormally with exit status {return_code}",
            details={"return_code": return_code, "output": full_text},
        )

    # General failure
    snippet = full_text.strip() or f"exit code {return_code}"
    return InferenceFailedError(
        f"Demucs separation failed on {device}: {snippet}",
        details={"device": device, "return_code": return_code, "output": full_text},
    )


def classify_error(exc: Exception) -> StemLabError:
    """Normalize an arbitrary exception into a structured StemLabError."""
    if isinstance(exc, StemLabError):
        return exc
    if isinstance(exc, FileNotFoundError):
        return SourceNotFoundError(str(exc), details={"original": type(exc).__name__})
    if isinstance(exc, FileExistsError):
        return PackageExistsError(str(exc), details={"original": type(exc).__name__})
    if isinstance(exc, PermissionError):
        return PermissionDeniedError(str(exc), details={"original": type(exc).__name__})
    if isinstance(exc, KeyboardInterrupt):
        return GenerationCancelledError("Operation cancelled by user", details={})

    msg = str(exc)
    if _CUDA_OOM_PATTERNS.search(msg):
        return CudaOutOfMemoryError(msg, details={"original": type(exc).__name__})
    if _DISK_FULL_PATTERNS.search(msg):
        return InsufficientDiskSpaceError(msg, details={"original": type(exc).__name__})
    if _DOWNLOAD_PATTERNS.search(msg):
        return ModelDownloadError(msg, details={"original": type(exc).__name__})

    return InferenceFailedError(msg, details={"original": type(exc).__name__})
