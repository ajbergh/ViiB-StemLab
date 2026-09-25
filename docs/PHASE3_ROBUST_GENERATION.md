# Phase 3 — Robust Generation Reference & Specification

**Status:** Complete — 2026-09-25  
**Deliverables:** Programmatic Cancellation, Disk Preflight, Failure Classification, GPU-to-CPU Fallback, Model Cache Management  
**Test Suite:** 61 passing unit & integration tests (`uv run pytest`)

---

## 1. Overview

Phase 3 transitions ViiB-StemLab from an MVP single-separation script into a resilient, production-grade generation pipeline. It establishes the programmatic isolation, preflight safety, and error normalization foundations required before Phase 4 introduces the desktop user interface and batch queue.

---

## 2. Programmatic Job Cancellation & Worker Isolation

### 2.1 CancellationToken Architecture

Programmatic cancellation is managed via `CancellationToken` (`src/viib_stemlab/cancellation.py`):

```python
from viib_stemlab.cancellation import CancellationToken

token = CancellationToken()

# Cooperative check
token.raise_if_cancelled()  # Raises GenerationCancelledError if cancelled

# Thread-safe callback registration
token.add_callback(lambda: print("Cancellation signaled"))

# Request cancellation
token.cancel(reason="User cancelled via UI")
```

- **Thread-safe**: Mutex-guarded internal state (`threading.Lock`) and synchronization event (`threading.Event`).
- **Immediate Callback Execution**: If a callback is registered on an already-cancelled token, it executes immediately within the calling thread.
- **Cooperative Checking**: Long-running operations inspect `token.is_cancelled` or call `token.raise_if_cancelled()` between processing segments.

### 2.2 Subprocess Lifecycle & Termination Protocol

Separation engines executing external processes (such as `DemucsEngine`) attach process termination hooks directly to the active cancellation token:

1. When separation starts, `DemucsEngine._execute_subprocess` registers a cancellation hook referencing the running `subprocess.Popen` instance.
2. When cancellation occurs:
   - The token invokes the termination hook.
   - The engine sends `SIGTERM` (or `TerminateProcess` on Windows) to the child process.
   - The engine waits up to 5.0 seconds for graceful exit.
   - If the worker does not exit within the timeout, the engine escalates to `SIGKILL` (`process.kill()`).
3. Output stream readers and iteration loops break immediately.
4. Any `.partial-*` staging directories and temporary engine scratch directories are cleanly deleted.

### 2.3 Host Process VRAM Recovery

To prevent GPU memory leaks when jobs terminate abnormally or are cancelled, `cleanup_vram()` (`src/viib_stemlab/cancellation.py`) performs host-side cleanup:

- Inspects `sys.modules` for active `torch` references without forcibly importing PyTorch.
- Invokes `torch.cuda.empty_cache()` and `torch.cuda.ipc_collect()` if CUDA is initialized.
- Gracefully handles MPS cache release on Apple Silicon where available.

---

## 3. Disk-Space Preflight

Out-of-disk failures during stem generation waste compute time and risk corrupting libraries. Preflight verification estimates required storage before any model invocation (`src/viib_stemlab/preflight.py`).

### 3.1 Duration & Storage Estimation

`estimate_required_disk_space(source, ...)` computes storage requirements using:

$$ \text{Stem Bytes} = \text{duration} \times \text{sample\_rate} \times \text{channels} \times \text{bytes\_per\_sample} \times 6 $$

1. **Duration Estimation (`estimate_source_duration`)**:
   - **WAV**: Exact duration read directly from the WAV header (`data` frame count / sample rate).
   - **FFprobe**: If available, inspects container metadata (`format=duration`).
   - **Compressed Fallback**: Uses format-specific bitrates (FLAC: ~100 KB/s; MP3/OGG: ~35 KB/s) based on input file size, clamped to a minimum duration of 30 seconds.
2. **Storage Allocation Breakdown**:
   - `estimated_stem_bytes`: Size of 6 uncompressed 16-bit 44.1 kHz stereo WAV stems.
   - `estimated_work_bytes`: Scratch space required by the separation engine.
   - `estimated_staging_bytes`: Space required for the atomic `.partial-*` staging directory.
   - `headroom_bytes`: Default safety buffer of 50 MB.
   - `required_output_bytes` = $\text{staging\_bytes} + \text{headroom\_bytes}$
   - `required_temp_bytes` = $\text{work\_bytes} + \text{headroom\_bytes}$

### 3.2 Filesystem Capacity Verification

`check_disk_space(output_root, temp_dir, estimate)` inspects disk space via `shutil.disk_usage`:

- Evaluates nearest existing filesystem ancestor for paths that have not yet been created.
- Compares free space on the target output drive against `required_output_bytes`.
- Compares free space on the temporary scratch drive against `required_temp_bytes`.
- Raises structured `InsufficientDiskSpaceError` with exact required vs. available bytes if limits are exceeded.
- Can be bypassed via `--skip-preflight` in the CLI or `skip_preflight=True` in `generate_package()`.

---

## 4. Structured Failure Classification & Error Taxonomy

Phase 3 introduces a normalized error taxonomy under `StemLabError` (`src/viib_stemlab/errors.py`). Every error provides:
- `code`: Machine-readable error code.
- `message`: Specific description of the failure condition.
- `diagnostic`: Actionable troubleshooting guidance for the user or UI.
- `details`: Structured metadata dictionary for logs and debugging.

### 4.1 Normalized Error Classes

| Error Code | Class | Standard Base | Diagnostic Action |
|---|---|---|---|
| `source_not_found` | `SourceNotFoundError` | `FileNotFoundError` | Verify input file path exists. |
| `source_unreadable` | `SourceUnreadableError` | `PermissionError` | Check file read permissions and file locks. |
| `unsupported_input` | `UnsupportedInputFormatError` | `ValueError` | Provide a supported audio format (`.wav`, `.flac`, `.mp3`, `.ogg`). |
| `model_missing` | `ModelMissingError` | `RuntimeError` | Download weights via `viib-stemlab model download <model>`. |
| `model_download_failed`| `ModelDownloadError` | `RuntimeError` | Check network connectivity and proxy settings. |
| `cuda_unavailable` | `CudaUnavailableError` | `DemucsUnavailableError` | Verify NVIDIA drivers or select `--device cpu`. |
| `cuda_oom` | `CudaOutOfMemoryError` | `RuntimeError` | Free VRAM, enable `--fallback-to-cpu`, or reduce load. |
| `mps_unavailable` | `MpsUnavailableError` | `DemucsUnavailableError` | Verify macOS version and Metal support. |
| `inference_failed` | `InferenceFailedError` | `RuntimeError` | Inspect detailed engine logs. |
| `worker_crashed` | `WorkerCrashedError` | `RuntimeError` | Check system memory stability and crash dump logs. |
| `cancelled` | `GenerationCancelledError` | `RuntimeError` | Operation was cancelled by user. |
| `output_missing` | `OutputMissingError` | `RuntimeError` | Verify engine emitted all 6 expected stems. |
| `output_geometry_mismatch` | `OutputGeometryMismatchError` | `PackageValidationError` | Stems must have identical sample rates and frame counts. |
| `checksum_failed` | `ChecksumMismatchError` | `ValueError` | Generated stem checksum does not match manifest. |
| `disk_full` | `InsufficientDiskSpaceError` | `OSError` | Free storage space on output and temp drives. |
| `permission_denied` | `PermissionDeniedError` | `PermissionError` | Ensure write permissions on output directory. |
| `package_exists` | `PackageExistsError` | `FileExistsError` | Use `--overwrite` to replace existing package. |
| `package_validation_failed` | `PackageValidationError` | `ValueError` | Review package schema and integrity rules. |

### 4.2 Subprocess Failure Classifier

`classify_process_failure(return_code, output_tail, device)` parses process termination signals and regex patterns across stdout/stderr:
- **CUDA OOM**: Matches `CUDA out of memory`, `torch.cuda.OutOfMemoryError`, `allocation exceeds`.
- **Disk Full**: Matches `No space left on device`, `Errno 28`, `disk full`.
- **Crash Detection**: Translates abnormal OS exit codes (e.g., Windows `0xC0000005` access violation `-1073741819`, Unix `SIGSEGV` `-11`, `SIGBUS` `-7`) into `WorkerCrashedError`.
- **Network Interruptions**: Matches connection resets, timeouts, and HTTP errors during auto-download attempts into `ModelDownloadError`.

---

## 5. Explicit GPU-to-CPU Fallback Policy

GPU acceleration should degrade gracefully to CPU without crashing a batch job or requiring manual intervention.

### 5.1 Mechanism

- Activated via `--fallback-to-cpu` CLI flag or `fallback_to_cpu=True` in `generate_package()`.
- When an active GPU separation (CUDA or MPS) raises:
  - `cuda_oom` (`CudaOutOfMemoryError`)
  - `cuda_unavailable` (`CudaUnavailableError`)
  - `mps_unavailable` (`MpsUnavailableError`)
- The engine executes the fallback sequence:
  1. Emits a `warning` progress update detailing the GPU failure.
  2. Invokes `cleanup_vram()` to release allocated GPU memory.
  3. Purges any partial files in the temporary work directory.
  4. Retries separation on `device="cpu"`.

### 5.2 Provenance Tracking

When fallback occurs:
- `SeparationResult` records `fallback_occurred=True` and `original_device="cuda"`.
- The final package manifest records the actual executing device:
  ```json
  "model": {
    "engine": "demucs",
    "name": "htdemucs_6s",
    "version": "4.0.1",
    "device": "cpu"
  }
  ```

---

## 6. Model Cache Preflight & Management

Model weights are substantial (~55 MB for Demucs transformers, up to several GB for ensemble models). Phase 3 centralizes cache resolution and pre-download management (`src/viib_stemlab/models.py`).

### 6.1 Cache Directory Resolution Order

1. Explicit `--cache-dir` parameter or CLI argument.
2. `VIIB_STEMLAB_CACHE_DIR` environment variable.
3. `TORCH_HOME/hub/checkpoints` environment variable.
4. PyTorch standard cache: `~/.cache/torch/hub/checkpoints` (Windows: `%USERPROFILE%\.cache\torch\hub\checkpoints`).

### 6.2 Atomic Model Checkpoint Downloads

- Downloads stream to a `.partial-<uuid>` file in the cache directory with progress reporting.
- Checkpoints are atomically renamed into their final hash-verified filename only upon complete transfer.
- Corrupted or partial downloads are deleted automatically if an exception or cancellation occurs.

### 6.3 Management Commands

```bash
# Check cache status across known models
viib-stemlab model status

# Pre-fetch weights for a specific model before queue execution
viib-stemlab model download htdemucs_6s

# View model cache directory and available disk in diagnostics
viib-stemlab doctor
```

---

## 7. Structured Progress Reporting

The `ProgressEmitter` (`src/viib_stemlab/progress.py`) provides typed progress events:

```python
@dataclass(frozen=True)
class ProgressUpdate:
    stage: str               # preflight, preparing, separating, packaging, validating, finalizing, warning, complete
    progress: float | None   # 0.0 to 1.0 (or None for indeterminate steps)
    message: str | None      # Human-readable progress description
    details: dict[str, Any]  # Key metrics (e.g. bytes downloaded, fallback status)
    timestamp: float         # Epoch time
```

`ProgressEmitter` supports both:
- **Modern 1-arg callbacks**: `callback(update: ProgressUpdate)`
- **Legacy 3-arg callbacks**: `callback(stage: str, val: float | None, msg: str | None)`
