from __future__ import annotations

from pathlib import Path

from viib_stemlab.engines.base import EngineCapabilities, SeparationResult
from viib_stemlab.services.generate import generate_package
from viib_stemlab.validation import validate_package


class FakeEngine:
    def __init__(self, stems: dict[str, Path]):
        self.stems = stems

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            available=True,
            engine="fake",
            version="1",
            devices=("cpu",),
            auto_device="cpu",
        )

    def separate(
        self,
        source: Path,
        work_dir: Path,
        *,
        device: str = "auto",
        progress=None,
    ) -> SeparationResult:
        if progress:
            progress("separating", 1.0, "fake separation complete")
        return SeparationResult(
            stems=self.stems,
            engine="fake",
            model="fake6",
            version="1",
            device="cpu",
        )


def test_generation_service_round_trip(
    tmp_path: Path,
    source_file: Path,
    stem_files: dict[str, Path],
) -> None:
    events = []

    def progress(stage, value, message) -> None:
        events.append((stage, value, message))

    package = generate_package(
        source=source_file,
        output_root=tmp_path / "library",
        engine=FakeEngine(stem_files),
        progress=progress,
    )

    manifest = validate_package(package, source_path=source_file)
    assert manifest.model.engine == "fake"
    assert events[0][0] == "preparing"
    assert events[-1][0] == "complete"
