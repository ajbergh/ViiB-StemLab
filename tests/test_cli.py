from __future__ import annotations

import json
from pathlib import Path

from conftest import write_test_wav

from viib_stemlab.cli import main
from viib_stemlab.constants import CANONICAL_STEMS
from viib_stemlab.validation import validate_package


def test_doctor_runs_without_demucs(capsys) -> None:
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "ViiB-StemLab" in output
    assert "PyTorch:" in output
    assert "CUDA available:" in output
    assert "MPS available:" in output
    assert "Auto device:" in output


def test_doctor_json_has_runtime_capabilities(capsys) -> None:
    assert main(["doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert "torch" in report
    assert "demucs" in report
    assert "cudaAvailable" in report["torch"]
    assert "mpsAvailable" in report["torch"]
    assert "autoDevice" in report["demucs"]
    assert ".mp3" in report["input"]["extensions"]
    assert ".ogg" in report["input"]["extensions"]
    assert "ffmpegAvailable" in report["input"]
    assert "ffprobeAvailable" in report["input"]


def test_package_build_wraps_existing_stems(
    tmp_path: Path,
    source_file: Path,
    capsys,
) -> None:
    stems_dir = tmp_path / "external-stems"
    for name in CANONICAL_STEMS:
        write_test_wav(stems_dir / f"{name}.wav", frames=64)

    output = tmp_path / "library"
    assert (
        main(
            [
                "package",
                "build",
                "--source",
                str(source_file),
                "--stems-dir",
                str(stems_dir),
                "--output",
                str(output),
                "--engine",
                "third-party",
                "--model",
                "six-stem-test",
                "--model-version",
                "1.2.3",
            ]
        )
        == 0
    )

    package = Path(capsys.readouterr().out.strip())
    manifest = validate_package(package, source_path=source_file)
    assert manifest.model.engine == "third-party"
    assert manifest.model.name == "six-stem-test"
    assert manifest.model.version == "1.2.3"
    assert manifest.model.device == "external"


def test_package_build_reports_missing_stems(
    tmp_path: Path,
    source_file: Path,
    capsys,
) -> None:
    stems_dir = tmp_path / "incomplete"
    write_test_wav(stems_dir / "vocals.wav")

    code = main(
        [
            "package",
            "build",
            "--source",
            str(source_file),
            "--stems-dir",
            str(stems_dir),
            "--output",
            str(tmp_path / "library"),
        ]
    )

    assert code == 1
    assert "package build failed:" in capsys.readouterr().err


def test_generate_reports_keyboard_interrupt(monkeypatch, capsys) -> None:
    def cancelled(**kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("viib_stemlab.cli.generate_package", cancelled)

    code = main(["generate", "track.wav", "--output", "stems"])

    assert code == 130
    assert "generation cancelled" in capsys.readouterr().err
