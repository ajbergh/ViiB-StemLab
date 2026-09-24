from __future__ import annotations

import tempfile
from pathlib import Path

from viib_stemlab.engines.base import ProgressCallback, StemEngine
from viib_stemlab.package import build_package_from_stems


def generate_package(
    *,
    source: Path,
    output_root: Path,
    engine: StemEngine,
    device: str = "auto",
    overwrite: bool = False,
    progress: ProgressCallback | None = None,
) -> Path:
    source = Path(source)
    output_root = Path(output_root)

    if progress:
        progress("preparing", None, f"Preparing {source.name}")

    with tempfile.TemporaryDirectory(prefix="viib-stemlab-engine-") as temp:
        result = engine.separate(
            source,
            Path(temp),
            device=device,
            progress=progress,
        )

        if progress:
            progress("packaging", 0.0, "Validating and packaging stems")

        package = build_package_from_stems(
            source=source,
            stems=result.stems,
            output_root=output_root,
            engine_name=result.engine,
            model_name=result.model,
            model_version=result.version,
            device=result.device,
            overwrite=overwrite,
        )

    if progress:
        progress("complete", 1.0, str(package))
    return package
