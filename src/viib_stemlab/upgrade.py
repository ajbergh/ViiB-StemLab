"""Upgrade StemLab 0.1.0 package manifests to ViiB Stem Package v1.

StemLab 0.1.0 wrote manifests that predate the MediaHub v1 contract, so
MediaHub rejects those packages (``manifest.stemLayout is required``). The
stem audio in those packages is already v1-compatible WAV; only
``manifest.json`` needs rewriting. No audio file is touched.

Each upgrade is transactional per package: the original manifest is kept as
``manifest.v0.json`` (never overwritten once present), the new manifest is
written atomically, and the package is re-validated against its files. If
validation fails, the original manifest is restored.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from viib_stemlab.constants import PACKAGE_SUFFIX
from viib_stemlab.errors import PackageValidationError
from viib_stemlab.manifest import is_legacy_manifest, upgrade_legacy_manifest
from viib_stemlab.validation import read_stem_wav_format, safe_member_path, validate_package

LEGACY_BACKUP_NAME = "manifest.v0.json"


@dataclass
class UpgradeOutcome:
    package: Path
    status: str  # "upgraded" | "would-upgrade" | "already-v1" | "failed"
    detail: str = ""


@dataclass
class UpgradeReport:
    outcomes: list[UpgradeOutcome] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == status)


def find_packages(path: Path) -> list[Path]:
    """A single package directory, or every package directory below ``path``."""
    path = Path(path)
    if path.name.endswith(PACKAGE_SUFFIX) and path.is_dir():
        return [path]
    return sorted(
        (candidate for candidate in path.rglob(f"*{PACKAGE_SUFFIX}") if candidate.is_dir()),
        key=lambda candidate: str(candidate).lower(),
    )


def upgrade_package(package_dir: Path, *, dry_run: bool = False, verify_hashes: bool = True) -> UpgradeOutcome:
    package_dir = Path(package_dir)
    manifest_path = package_dir / "manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return UpgradeOutcome(package_dir, "failed", f"cannot read manifest.json: {exc}")
    if not isinstance(data, dict):
        return UpgradeOutcome(package_dir, "failed", "manifest.json is not a JSON object")

    if not is_legacy_manifest(data):
        try:
            validate_package(package_dir, verify_hashes=False)
        except PackageValidationError as exc:
            return UpgradeOutcome(package_dir, "failed", "not a StemLab 0.1.0 manifest and not valid v1: " + "; ".join(exc.errors))
        return UpgradeOutcome(package_dir, "already-v1")

    stems = data.get("stems") if isinstance(data.get("stems"), dict) else {}
    formats: dict[str, tuple[int, int, int, str]] = {}
    for name, entry in stems.items():
        try:
            stem_path = safe_member_path(package_dir, str(entry.get("file", "")).replace("\\", "/"))
            info = read_stem_wav_format(stem_path)
        except (OSError, ValueError, AttributeError) as exc:
            return UpgradeOutcome(package_dir, "failed", f"{name}: {exc}")
        formats[name] = (info.sample_rate, info.channels, info.frames, info.encoding)

    try:
        upgraded = upgrade_legacy_manifest(data, formats)
    except ValueError as exc:
        return UpgradeOutcome(package_dir, "failed", str(exc))
    problems = upgraded.structural_errors()
    if problems:
        return UpgradeOutcome(package_dir, "failed", "; ".join(problems))
    if dry_run:
        return UpgradeOutcome(package_dir, "would-upgrade")

    original = manifest_path.read_bytes()
    backup = package_dir / LEGACY_BACKUP_NAME
    if not backup.exists():
        backup.write_bytes(original)
    staged = package_dir / ".manifest.json.upgrading"
    staged.write_text(upgraded.to_json(), encoding="utf-8")
    os.replace(staged, manifest_path)
    try:
        validate_package(package_dir, verify_hashes=verify_hashes)
    except PackageValidationError as exc:
        manifest_path.write_bytes(original)
        return UpgradeOutcome(package_dir, "failed", "upgraded manifest failed validation (original restored): " + "; ".join(exc.errors))
    return UpgradeOutcome(package_dir, "upgraded")


def upgrade_packages(path: Path, *, dry_run: bool = False, verify_hashes: bool = True) -> UpgradeReport:
    report = UpgradeReport()
    for package_dir in find_packages(path):
        report.outcomes.append(upgrade_package(package_dir, dry_run=dry_run, verify_hashes=verify_hashes))
    return report
