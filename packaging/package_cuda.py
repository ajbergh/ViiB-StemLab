"""Create the downloadable CUDA worker and its exact release manifest (no upload)."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from viib_stemlab.cuda_runtime import DEFAULT_MANIFEST_URL, file_sha256, validate_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import torch

    if torch.__version__ != "2.6.0+cu124" or torch.version.cuda != "12.4":
        parser.error("Build with the pinned torch 2.6.0+cu124 packaging environment")
    inventory = args.runtime / "notices/python-environment.json"
    if not (args.runtime / "stemlab-backend.exe").is_file() or not inventory.is_file():
        parser.error("A built Windows backend and notices are required")
    packages = {p["name"].lower(): p["version"] for p in json.loads(inventory.read_text("utf-8"))}
    if packages.get("torch") != "2.6.0+cu124":
        parser.error("The frozen backend inventory does not match the CUDA build environment")
    args.output.mkdir(parents=True, exist_ok=True)
    # Never leave a stale publishable manifest if a rebuild fails or is interrupted.
    (args.output / "windows-cuda.json").unlink(missing_ok=True)
    archive = args.output / "stemlab-cuda-1-torch2.6-cu124-windows-x64.zip"
    staging_archive = archive.with_suffix(".zip.partial")
    files = sorted(p for p in args.runtime.rglob("*") if p.is_file())
    with zipfile.ZipFile(staging_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as bundle:
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
            parts.append({"url": DEFAULT_MANIFEST_URL.rsplit("/", 1)[0] + "/" + part.name,
                          "size": part.stat().st_size, "sha256": file_sha256(part)})
    manifest = validate_manifest({
        "protocol": 1, "platform": "windows-x64", "version": "1-torch2.6-cu124",
        "parts": parts,
        "sha256": file_sha256(archive), "size": archive.stat().st_size,
        "unpackedSize": sum(p.stat().st_size for p in files),
        "executable": "stemlab-backend.exe", "minimumDriver": "551.78",
    })
    staging_manifest = args.output / "windows-cuda.json.partial"
    staging_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    staging_manifest.replace(args.output / "windows-cuda.json")
    archive.unlink()  # Publish only the parts listed in the manifest.
    print(f"CUDA release files ready: {args.output.resolve()}")


if __name__ == "__main__":
    main()
