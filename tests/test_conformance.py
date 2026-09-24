from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from viib_stemlab.manifest import StemManifest
from viib_stemlab.validation import PackageValidationError, validate_package

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SCHEMA = json.loads((ROOT / "docs" / "viib-stem-package-v1.schema.json").read_text())
SOURCE = FIXTURES / "source" / "fixture-source.bin"


def _manifest(name: str) -> dict:
    return json.loads((FIXTURES / name / "manifest.json").read_text(encoding="utf-8"))


def test_json_schema_accepts_valid_fixture() -> None:
    jsonschema.validate(_manifest("package-v1-valid.viibstems"), SCHEMA)


def test_runtime_accepts_valid_fixture_and_source() -> None:
    manifest = validate_package(
        FIXTURES / "package-v1-valid.viibstems",
        source_path=SOURCE,
    )
    assert manifest.schemaVersion == 1
    assert manifest.audio.frames == 32


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("package-v1-bad-checksum.viibstems", "vocals: SHA-256 mismatch"),
        ("package-v1-missing-stem.viibstems", "missing canonical stems: other"),
        ("package-v1-path-traversal.viibstems", "unsafe package-relative path"),
        ("package-v1-bad-geometry.viibstems", "piano: frame mismatch"),
    ],
)
def test_runtime_rejects_invalid_conformance_fixtures(
    fixture: str,
    expected: str,
) -> None:
    with pytest.raises(PackageValidationError) as exc:
        validate_package(FIXTURES / fixture)
    assert any(expected in error for error in exc.value.errors)


def test_runtime_detects_stale_source_fixture() -> None:
    with pytest.raises(PackageValidationError) as exc:
        validate_package(
            FIXTURES / "package-v1-stale-source.viibstems",
            source_path=SOURCE,
        )
    assert "source SHA-256 does not match manifest" in exc.value.errors


def test_parser_ignores_unknown_optional_fields_for_known_schema() -> None:
    data = _manifest("package-v1-valid.viibstems")
    data["futureOptionalField"] = {"safe": True}
    data["source"]["futureOptionalField"] = "safe"
    data["stems"]["vocals"]["futureOptionalField"] = 1

    manifest = StemManifest.from_dict(data)
    assert manifest.structural_errors() == []


def test_json_schema_rejects_missing_canonical_stem() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_manifest("package-v1-missing-stem.viibstems"), SCHEMA)
