"""Build and inspect native Linux x64 Full/On-demand Debian packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from build_macos import remove_generated, verify_payload

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str | Path) -> None:
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def inspect_deb(package: Path, flavor: str, destination: Path) -> Path:
    remove_generated(destination)
    run("dpkg-deb", "--info", package)
    architecture = subprocess.check_output(["dpkg-deb", "--field", str(package), "Architecture"], text=True).strip()
    if architecture != "amd64":
        raise ValueError(f"Unexpected Debian architecture: {architecture}")
    run("dpkg-deb", "--extract", package, destination)
    configs = list(destination.rglob("installer.json"))
    if len(configs) != 1:
        raise ValueError("Debian package must contain exactly one installer.json")
    resources = configs[0].parent
    if json.loads(configs[0].read_text())["flavor"] != flavor:
        raise ValueError("Debian package contains the wrong installer flavor")
    executable = destination / "usr/bin/viib-stemlab-desktop"
    if not executable.is_file() or executable.stat().st_mode & 0o111 == 0:
        raise ValueError("Debian application executable is missing or not executable")
    if flavor == "full":
        verify_payload(resources / "runtime")
        for relative in ("stemlab-backend", "_internal/audio-tools/ffmpeg", "_internal/audio-tools/ffprobe"):
            if (resources / "runtime" / relative).stat().st_mode & 0o111 == 0:
                raise ValueError(f"Debian package lost executable permissions: {relative}")
    elif (resources / "runtime").exists():
        raise ValueError("On-demand Debian package unexpectedly contains a runtime")
    return resources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", choices=("full", "ondemand", "both"), default="both")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("Build on native Linux x64 (Ubuntu 22.04 baseline)")
    for tool in ("cc", "make", "cargo", "node", "npm", "dpkg-deb", "ldd"):
        if not shutil.which(tool):
            parser.error(f"Missing prerequisite: {tool}")
    run("node", "-e", "if(parseInt(process.versions.node)<22) process.exit(1)")
    if args.check_only:
        return
    import fcntl

    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    with (build / "linux-build.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        python = build / "linux-packaging-venv/bin/python"
        if not python.exists():
            run(sys.executable, "-m", "venv", python.parent.parent)
        run(python, "-m", "pip", "install", "torch==2.6.0+cpu", "--index-url", "https://download.pytorch.org/whl/cpu")
        run(python, "-m", "pip", "install", "-e", ".[demucs,packaging]")
        decoders = build / "linux-decoder"
        run(python, "packaging/build_linux_decoders.py", "--output", decoders)
        run("npm", "--prefix", "desktop", "ci", "--no-audit", "--no-fund")
        run("npm", "--prefix", "desktop", "run", "test")
        stage = build / "linux-runtime-next"
        remove_generated(stage)
        run(python, "packaging/build_backend.py", "--ffmpeg-dir", decoders,
            "--ffmpeg-notices", decoders / "DECODER_NOTICES.txt", "--output", stage)
        run(python, "packaging/smoke_backend.py", stage / "stemlab-backend", "--require-runtime")
        for filename, command in (
            ("frontend-sbom.json", ["npm", "--prefix", "desktop", "sbom", "--sbom-format", "cyclonedx"]),
            ("rust-dependencies.json", ["cargo", "metadata", "--locked", "--manifest-path", "desktop/src-tauri/Cargo.toml",
                                        "--format-version", "1", "--filter-platform", "x86_64-unknown-linux-gnu"]),
        ):
            with (stage / "notices" / filename).open("w") as output:
                subprocess.run(command, cwd=ROOT, stdout=output, check=True)
        run(python, "packaging/prepare_cpu_payload.py", "--runtime", stage, "--platform", "linux-x64",
            "--archive-output", ROOT / "dist/linux-components")
        run(python, "packaging/smoke_backend.py", stage / "stemlab-backend", "--require-runtime",
            "--model-cache-dir", stage / "models", "--separate", "--format", "flac")
        runtime = ROOT / "desktop/src-tauri/runtime"
        previous = build / "linux-runtime-previous"
        remove_generated(previous)
        if runtime.exists():
            runtime.rename(previous)
        try:
            stage.rename(runtime)
        except OSError:
            if previous.exists() and not runtime.exists():
                previous.rename(runtime)
            raise
        run("npm", "--prefix", "desktop", "run", "tauri", "--", "build",
            "--config", "src-tauri/tauri.linux-full.conf.json", "--no-bundle")
        release = ROOT / "desktop/src-tauri/target/release"
        output = ROOT / "dist/linux"
        output.mkdir(parents=True, exist_ok=True)
        version = json.loads((ROOT / "desktop/package.json").read_text())["version"]
        for flavor in (("full", "ondemand") if args.installer == "both" else (args.installer,)):
            remove_generated(release / "runtime")
            remove_generated(release / "bundle/deb")
            run("npm", "--prefix", "desktop", "run", "tauri", "--", "bundle",
                "--config", f"src-tauri/tauri.linux-{flavor}.conf.json", "--bundles", "deb")
            packages = list((release / "bundle/deb").glob("*.deb"))
            if len(packages) != 1:
                raise ValueError("Could not identify the generated Debian package")
            destination = output / f"ViiB-StemLab_{version}_amd64-{flavor}.deb"
            shutil.copy2(packages[0], destination)
            resources = inspect_deb(destination, flavor, build / f"linux-{flavor}-qa")
            if flavor == "full":
                (build / "linux-full-resources.txt").write_text(str(resources))
            with destination.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            destination.with_suffix(".deb.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
        remove_generated(previous)
        print("Linux x64 Debian candidates and runtime ready; no assets published.")


if __name__ == "__main__":
    main()
