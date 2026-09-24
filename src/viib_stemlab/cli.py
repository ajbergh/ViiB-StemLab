from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from shutil import which

from viib_stemlab import __version__
from viib_stemlab.constants import CANONICAL_STEMS, DEFAULT_MODEL, SUPPORTED_INPUT_EXTENSIONS
from viib_stemlab.engines.demucs import DemucsEngine, probe_torch_runtime
from viib_stemlab.package import build_package_from_stems
from viib_stemlab.services.generate import generate_package
from viib_stemlab.validation import PackageValidationError, validate_package


def _doctor(as_json: bool) -> int:
    caps = DemucsEngine().capabilities()
    torch_runtime = probe_torch_runtime()
    report = {
        "stemLabVersion": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "torch": {
            "available": torch_runtime.available,
            "version": torch_runtime.version,
            "cudaAvailable": torch_runtime.cuda_available,
            "cudaRuntime": torch_runtime.cuda_version,
            "mpsAvailable": torch_runtime.mps_available,
            "detail": torch_runtime.detail,
        },
        "demucs": {
            "available": caps.available,
            "version": caps.version,
            "devices": list(caps.devices),
            "autoDevice": caps.auto_device,
            "detail": caps.detail,
        },
        "input": {
            "extensions": list(SUPPORTED_INPUT_EXTENSIONS),
            "ffmpegAvailable": which("ffmpeg") is not None,
            "ffprobeAvailable": which("ffprobe") is not None,
        },
    }
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"ViiB-StemLab {__version__}")
        print(f"Python: {report['python']}")
        print(f"Platform: {report['platform']} ({report['machine']})")
        print(
            "PyTorch: "
            + (f"{torch_runtime.version}" if torch_runtime.available else "not installed")
        )
        print(f"CUDA available: {'yes' if torch_runtime.cuda_available else 'no'}")
        if torch_runtime.cuda_version:
            print(f"CUDA runtime: {torch_runtime.cuda_version}")
        print(f"MPS available: {'yes' if torch_runtime.mps_available else 'no'}")
        print(f"Demucs: {'available' if caps.available else 'not available'}")
        print(f"Demucs version: {caps.version or '-'}")
        print(f"Devices: {', '.join(caps.devices)}")
        print(f"Auto device: {caps.auto_device}")
        print(f"Supported inputs: {', '.join(SUPPORTED_INPUT_EXTENSIONS)}")
        print(f"FFmpeg available: {'yes' if report['input']['ffmpegAvailable'] else 'no'}")
        print(f"FFprobe available: {'yes' if report['input']['ffprobeAvailable'] else 'no'}")
        detail = caps.detail or torch_runtime.detail
        if detail:
            print(f"Detail: {detail}")
    return 0


def _validate(package: Path, source: Path | None, no_hashes: bool) -> int:
    try:
        manifest = validate_package(
            package,
            source_path=source,
            verify_hashes=not no_hashes,
        )
    except PackageValidationError as exc:
        print("INVALID", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    print(f"VALID {manifest.packageId}")
    return 0


def _inspect(package: Path) -> int:
    try:
        manifest = validate_package(package, verify_hashes=False)
    except PackageValidationError as exc:
        print("Package is not structurally valid:", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    print(json.dumps(manifest.to_dict(), indent=2))
    return 0


def _package_build(args: argparse.Namespace) -> int:
    stems = {name: args.stems_dir / f"{name}.wav" for name in CANONICAL_STEMS}
    try:
        package = build_package_from_stems(
            source=args.source,
            stems=stems,
            output_root=args.output,
            engine_name=args.engine,
            model_name=args.model,
            model_version=args.model_version,
            device=args.device,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"package build failed: {exc}", file=sys.stderr)
        return 1

    print(package)
    return 0


def _generate(args: argparse.Namespace) -> int:
    engine = DemucsEngine(model=args.model)
    last_percent: dict[str, int] = {}

    def progress(stage: str, value: float | None, message: str | None) -> None:
        if value is None:
            if message:
                print(f"[{stage}] {message}", file=sys.stderr)
            return
        percent = int(value * 100)
        if last_percent.get(stage) == percent:
            return
        last_percent[stage] = percent
        suffix = f" - {message}" if message else ""
        print(f"[{stage}] {percent}%{suffix}", file=sys.stderr)

    try:
        package = generate_package(
            source=args.source,
            output_root=args.output,
            engine=engine,
            device=args.device,
            overwrite=args.overwrite,
            progress=progress,
        )
    except KeyboardInterrupt:
        print("generation cancelled", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"generation failed: {exc}", file=sys.stderr)
        return 1
    print(package)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="viib-stemlab",
        description="Prepare versioned local stem packages for ViiB MediaHub.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Inspect local separation capabilities.")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    generate = sub.add_parser("generate", help="Generate a ViiB Stem Package.")
    generate.add_argument("source", type=Path)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--model", default=DEFAULT_MODEL)
    generate.add_argument(
        "--device", choices=("auto", "cpu", "cuda", "mps"), default="auto"
    )
    generate.add_argument("--overwrite", action="store_true")

    package = sub.add_parser("package", help="Build, inspect, or validate a stem package.")
    package_sub = package.add_subparsers(dest="package_command", required=True)

    build = package_sub.add_parser(
        "build",
        help="Package an existing six-stem WAV directory without running a separator.",
    )
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--stems-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--engine", default="external")
    build.add_argument("--model", default="external-six-stem")
    build.add_argument("--model-version", default="unknown")
    build.add_argument("--device", default="external")
    build.add_argument("--overwrite", action="store_true")

    validate = package_sub.add_parser("validate", help="Validate a ViiB Stem Package.")
    validate.add_argument("package", type=Path)
    validate.add_argument("--source", type=Path)
    validate.add_argument("--no-hashes", action="store_true")

    inspect = package_sub.add_parser("inspect", help="Print normalized package metadata.")
    inspect.add_argument("package", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor(args.as_json)
    if args.command == "generate":
        return _generate(args)
    if args.command == "package" and args.package_command == "build":
        return _package_build(args)
    if args.command == "package" and args.package_command == "validate":
        return _validate(args.package, args.source, args.no_hashes)
    if args.command == "package" and args.package_command == "inspect":
        return _inspect(args.package)
    return 2
