"""Create the downloadable CUDA worker and its exact release manifest (no upload)."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from viib_stemlab.cuda_profiles import PROFILES
from viib_stemlab.cuda_runtime import file_sha256, validate_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, default="legacy")
    parser.add_argument("--compression-level", type=int, choices=range(10), default=6,
                        help="ZIP compression level; 0 is faster for local installation, 6 is the release default")
    args = parser.parse_args()
    import torch

    profile = PROFILES[args.profile]
    expected = f"{profile['torch']}+{profile['flavor']}"
    if torch.__version__ != expected or torch.version.cuda != profile["cuda"]:
        parser.error(f"Build with the pinned torch {expected} packaging environment")
    required = {"sm_75", "sm_86"} | ({"sm_120"} if args.profile == "modern" else set())
    # get_arch_list() returns [] on CPU-only build runners. Inspect the pinned
    # wheel's compiled targets without requiring a driver/GPU on packaging CI.
    compiled = set((getattr(torch._C, "_cuda_getArchFlags", lambda: "")() or "").split())
    if not required.issubset(compiled):
        parser.error("Torch wheel does not contain the expected RTX GPU architectures")
    inventory = args.runtime / "notices/python-environment.json"
    if not (args.runtime / "stemlab-backend.exe").is_file() or not inventory.is_file():
        parser.error("A built Windows backend and notices are required")
    packages = {p["name"].lower(): p["version"] for p in json.loads(inventory.read_text("utf-8"))}
    if packages.get("torch") != expected:
        parser.error("The frozen backend inventory does not match the CUDA build environment")
    if packages.get("demucs") != "4.1.0":
        parser.error("The frozen backend must contain Demucs 4.1.0")
    args.output.mkdir(parents=True, exist_ok=True)
    # Never leave a stale publishable manifest if a rebuild fails or is interrupted.
    (args.output / "windows-cuda.json").unlink(missing_ok=True)
    archive = args.output / f"stemlab-cuda-{profile['version']}-windows-x64.zip"
    staging_archive = archive.with_suffix(".zip.partial")
    files = sorted(p for p in args.runtime.rglob("*") if p.is_file())
    compression = zipfile.ZIP_STORED if args.compression_level == 0 else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(staging_archive, "w", compression=compression,
                         compresslevel=args.compression_level or None, allowZip64=True) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(args.runtime).as_posix())
    staging_archive.replace(archive)
    parts = []
    with archive.open("rb") as stream:
        index = 0
        while chunk := stream.read(1024 * 1024):
            index += 1
            part = archive.with_suffix(f".zip.part{index:02d}")
            staged_part = part.with_suffix(part.suffix + ".partial")
            with staged_part.open("wb") as out:
                out.write(chunk)
                remaining = 1024**3 - len(chunk)
                while remaining and (chunk := stream.read(min(1024 * 1024, remaining))):
                    out.write(chunk)
                    remaining -= len(chunk)
            staged_part.replace(part)
            parts.append({"url": profile["manifestUrl"].rsplit("/", 1)[0] + "/" + part.name,
                          "size": part.stat().st_size, "sha256": file_sha256(part)})
    manifest = validate_manifest({
        "protocol": 1, "platform": "windows-x64", "version": profile["version"],
        "runtimeVersion": profile["version"], "computeCapabilities": profile["capabilities"],
        "parts": parts,
        "sha256": file_sha256(archive), "size": archive.stat().st_size,
        "unpackedSize": sum(p.stat().st_size for p in files),
        "executable": "stemlab-backend.exe", "minimumDriver": profile["minimumDriver"],
    })
    staging_manifest = args.output / "windows-cuda.json.partial"
    staging_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    staging_manifest.replace(args.output / "windows-cuda.json")
    archive.unlink()  # Publish only the parts listed in the manifest.
    print(f"CUDA release files ready: {args.output.resolve()}")


if __name__ == "__main__":
    main()
