from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from typing import Any

from viib_stemlab.cancellation import CancellationToken, cleanup_vram
from viib_stemlab.constants import SUPPORTED_INPUT_EXTENSIONS
from viib_stemlab.engines.base import ProgressCallback, StemEngine
from viib_stemlab.errors import (
    GenerationCancelledError,
    SourceNotFoundError,
    UnsupportedInputFormatError,
    classify_error,
)
from viib_stemlab.models import KNOWN_MODELS, ModelCacheManager
from viib_stemlab.package import build_package_from_stems
from viib_stemlab.preflight import check_disk_space, estimate_required_disk_space
from viib_stemlab.progress import ProgressEmitter


def validate_source_input(source: Path) -> Path:
    source = Path(source)
    if not source.is_file():
        raise SourceNotFoundError(f"Source file not found: {source}")

    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_INPUT_EXTENSIONS:
        supported = ", ".join(SUPPORTED_INPUT_EXTENSIONS)
        label = suffix or "<no extension>"
        raise UnsupportedInputFormatError(
            f"unsupported input format {label!r}; supported formats: {supported}"
        )
    return source


def generate_package(
    *,
    source: Path,
    output_root: Path,
    engine: StemEngine,
    device: str = "auto",
    overwrite: bool = False,
    fallback_to_cpu: bool = False,
    cancellation_token: CancellationToken | None = None,
    cache_dir: Path | None = None,
    skip_preflight: bool = False,
    progress: ProgressCallback | None = None,
) -> Path:
    emitter = ProgressEmitter(progress)

    if cancellation_token:
        cancellation_token.raise_if_cancelled()

    source = validate_source_input(source)
    output_root = Path(output_root)

    emitter.emit("preparing", None, f"Preparing {source.name}")

    # Preflight stage: disk space & model weight checks
    if not skip_preflight:
        emitter.emit("preflight", None, f"Checking disk space and model cache for {source.name}")
        estimate = estimate_required_disk_space(source)
        check_disk_space(output_root=output_root, estimate=estimate)

        model_name = getattr(engine, "model", None)
        if model_name and model_name in KNOWN_MODELS:
            cache_mgr = ModelCacheManager(cache_dir)
            cache_mgr.preflight_model(model_name, allow_download=True, progress=progress)

    if cancellation_token:
        cancellation_token.raise_if_cancelled()

    try:
        with tempfile.TemporaryDirectory(prefix="viib-stemlab-engine-") as temp:
            temp_path = Path(temp)

            sig = inspect.signature(engine.separate)
            sep_kwargs: dict[str, Any] = {"device": device, "progress": progress}
            has_var_kw = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            if "cancellation_token" in sig.parameters or has_var_kw:
                sep_kwargs["cancellation_token"] = cancellation_token
            if "fallback_to_cpu" in sig.parameters or has_var_kw:
                sep_kwargs["fallback_to_cpu"] = fallback_to_cpu

            result = engine.separate(
                source,
                temp_path,
                **sep_kwargs,
            )

            if cancellation_token:
                cancellation_token.raise_if_cancelled()

            emitter.emit("packaging", 0.0, "Validating and packaging stems")

            package = build_package_from_stems(
                source=source,
                stems=result.stems,
                output_root=output_root,
                engine_name=result.engine,
                model_name=result.model,
                model_version=result.version,
                device=result.device,
                overwrite=overwrite,
                cancellation_token=cancellation_token,
                progress=progress,
            )

        emitter.emit("complete", 1.0, str(package))
        return package
    except KeyboardInterrupt:
        cleanup_vram()
        raise GenerationCancelledError("Generation cancelled by user")
    except GenerationCancelledError:
        cleanup_vram()
        raise
    except Exception as exc:
        cleanup_vram()
        raise classify_error(exc) from exc
