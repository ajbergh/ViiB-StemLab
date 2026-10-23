"""Prepare a verified offline CPU payload and optionally its on-demand release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from viib_stemlab import __version__
from viib_stemlab.constants import DEFAULT_MODEL
from viib_stemlab.models import FT_CHECKPOINTS, ModelCacheManager


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(
    runtime: Path, model_source: Path | None = None, target_platform: str = "windows-x64"
) -> dict:
    if target_platform not in ("windows-x64", "macos-arm64"):
        raise ValueError("Unsupported processing payload platform")
    executable = "stemlab-backend.exe" if target_platform == "windows-x64" else "stemlab-backend"
    if not (runtime / executable).is_file():
        raise ValueError(f"A built {target_platform} backend is required")
    inventory = json.loads((runtime / "notices/python-environment.json").read_text("utf-8"))
    expected_torch = "2.6.0+cpu" if target_platform == "windows-x64" else "2.6.0"
    if not any(p["name"].lower() == "torch" and p["version"] == expected_torch for p in inventory):
        raise ValueError("CPU payload requires the pinned Torch 2.6.0+cpu runtime")
    if not any(p["name"].lower() == "demucs" and p["version"] == "4.1.0" for p in inventory):
        raise ValueError("Processing payload requires Demucs 4.1.0")
    model_paths = []
    checkpoint_notices = []
    for model in FT_CHECKPOINTS:
        target = runtime / "models" / model["cache_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        source_dir = model_source if model_source is not None else ModelCacheManager().cache_dir
        source = source_dir / model["cache_path"]
        if not source.is_file():
            source = source_dir / model["filename"]

        def valid(path: Path, model=model) -> bool:
            return (
                path.is_file()
                and path.stat().st_size == model["expected_size_bytes"]
                and sha256(path) == model["sha256"]
            )

        if valid(target):
            pass
        elif valid(source):
            shutil.copy2(source, target)
        else:
            with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
                download = Path(temporary) / model["filename"]
                with (
                    urllib.request.urlopen(model["url"], timeout=60) as response,
                    download.open("wb") as out,
                ):
                    shutil.copyfileobj(response, out)
                if not valid(download):
                    raise ValueError("Model weight size/checksum mismatch")
                download.replace(target)
        model_paths.append(f"models/{model['cache_path']}")
        checkpoint_notices.append(f"Checkpoint: {model['url']}\n\nSHA-256: {model['sha256']}\n\n")
    ModelCacheManager(runtime / "models").write_hf_reference()
    notices = runtime / "notices/MODEL_NOTICES.md"
    notices.write_text(
        f"# Bundled {DEFAULT_MODEL} weights\n\n"
        + "".join(checkpoint_notices)
        + "Model source and license: https://github.com/adefossez/demucs ; "
        "https://github.com/adefossez/demucs/blob/main/LICENSE\n"
        "See the bundled Demucs license and Python inventory. Review redistribution notices before publishing.\n",
        encoding="utf-8",
    )
    files = {
        p.relative_to(runtime).as_posix(): {"size": p.stat().st_size, "sha256": sha256(p)}
        for p in sorted(runtime.rglob("*"))
        if p.is_file() and p != runtime / "payload.json"
    }
    payload = {
        "protocol": 1,
        "appVersion": __version__,
        "platform": target_platform,
        "version": f"{__version__}-{'cpu' if target_platform == 'windows-x64' else 'mps'}-demucs410-1",
        "executable": executable,
        "models": model_paths,
        "files": files,
    }
    (runtime / "payload.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def archive_payload(runtime: Path, output: Path, payload: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    windows = payload["platform"] == "windows-x64"
    manifest = output / ("windows-cpu.json" if windows else "macos-arm64.json")
    manifest.unlink(missing_ok=True)
    name = (
        f"stemlab-cpu-{payload['appVersion']}-windows-x64.zip"
        if windows
        else f"stemlab-runtime-{payload['appVersion']}-macos-arm64.zip"
    )
    archive = output / name
    staged = output / (name + ".partial")
    files = sorted(p for p in runtime.rglob("*") if p.is_file())
    with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(runtime).as_posix())
    staged.replace(archive)
    release = {
        "protocol": 1,
        "appVersion": payload["appVersion"],
        "version": payload["version"],
        "platform": payload["platform"],
        "sha256": sha256(archive),
        "size": archive.stat().st_size,
        "unpackedSize": sum(p.stat().st_size for p in files),
        "url": f"https://github.com/ajbergh/ViiB-StemLab/releases/download/{'cpu' if windows else 'macos'}-runtime-{payload['appVersion']}/{name}",
    }
    staged_manifest = manifest.with_suffix(".json.partial")
    staged_manifest.write_text(json.dumps(release, indent=2), encoding="utf-8")
    staged_manifest.replace(manifest)
    print(f"On-demand release assets: {output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument(
        "--model", type=Path, help="Directory containing the htdemucs_ft YAML and four safetensors checkpoints"
    )
    parser.add_argument("--archive-output", type=Path)
    parser.add_argument("--platform", choices=("windows-x64", "macos-arm64"), default="windows-x64")
    args = parser.parse_args()
    payload = prepare(args.runtime, args.model, args.platform)
    if args.archive_output:
        archive_payload(args.runtime, args.archive_output, payload)
    print("Verified CPU engine, decoders, model and notices are ready.")


if __name__ == "__main__":
    main()
