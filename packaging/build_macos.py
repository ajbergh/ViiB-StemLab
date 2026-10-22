"""Build standalone Apple Silicon Full/On-demand app and DMG candidates on a Mac."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, env: dict | None = None) -> None:
    subprocess.run(list(map(str, args)), cwd=ROOT, env=env, check=True)


def remove_generated(path: Path) -> None:
    resolved = path.resolve()
    if path.is_symlink() or not any(resolved.is_relative_to(parent) and resolved != parent for parent in
                                  (ROOT / "build", ROOT / "desktop/src-tauri/target")):
        raise ValueError(f"Refusing unmanaged build-directory deletion: {path}")
    if path.exists():
        shutil.rmtree(path)


def verify_payload(directory: Path) -> None:
    payload = json.loads((directory / "payload.json").read_text("utf-8"))
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual != set(payload["files"]) | {"payload.json"}:
        raise ValueError("Bundled runtime file set differs from its inventory")
    for name, entry in payload["files"].items():
        path = directory / name
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != entry["size"] or checksum != entry["sha256"]:
            raise ValueError(f"Bundling/signing changed processing component: {name}")


def inspect_dmg(dmg: Path, flavor: str, build: Path) -> None:
    mount = build / f"macos-mount-{flavor}"
    mount.mkdir(exist_ok=True)
    run("hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", mount, dmg)
    try:
        apps = list(mount.glob("*.app"))
        if len(apps) != 1:
            raise ValueError("DMG does not contain exactly one application")
        app = apps[0]
        run("codesign", "--verify", "--deep", "--strict", app)
        resources = app / "Contents/Resources"
        if json.loads((resources / "installer.json").read_text())["flavor"] != flavor:
            raise ValueError("DMG contains the wrong installer flavor")
        if flavor == "full":
            verify_payload(resources / "runtime")
            # Native bootstrap tests inspect the finished DMG contents, not the
            # pre-bundle source tree. Keep a private QA copy before unmounting.
            qa = build / "macos-full-qa.app"
            remove_generated(qa)
            shutil.copytree(app, qa, symlinks=True)
        elif (resources / "runtime").exists():
            raise ValueError("On-demand DMG unexpectedly contains the full runtime")
        if os.environ.get("APPLE_ID") or os.environ.get("APPLE_API_KEY"):
            run("xcrun", "stapler", "validate", app)
            run("spctl", "--assess", "--type", "execute", app)
    finally:
        run("hdiutil", "detach", mount)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", choices=("full", "ondemand", "both"), default="both")
    parser.add_argument("--ffmpeg-dir", type=Path, help="Prebuilt standalone decoders with DECODER_NOTICES.txt")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("Build on native Apple Silicon macOS (not Rosetta or Windows)")
    for tool in ("clang", "make", "cargo", "node", "npm", "codesign", "otool"):
        if not shutil.which(tool):
            parser.error(f"Missing build prerequisite: {tool}")
    run("node", "-e", "if(parseInt(process.versions.node)<22) process.exit(1)")
    if args.check_only:
        print("Apple Silicon packaging prerequisites found.")
        return
    os.environ["MACOSX_DEPLOYMENT_TARGET"] = "14.0"
    import fcntl

    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    with (build / "macos-build.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        python = build / "macos-packaging-venv/bin/python"
        if not python.exists():
            run(sys.executable, "-m", "venv", python.parent.parent)
        run(python, "-m", "pip", "install", "torch==2.6.0", "torchaudio==2.6.0")
        run(python, "-m", "pip", "install", "-e", ".[demucs,packaging]")
        decoders = args.ffmpeg_dir.resolve() if args.ffmpeg_dir else build / "macos-decoder"
        if not args.ffmpeg_dir:
            run(python, "packaging/build_macos_decoders.py", "--output", decoders)
        run("npm", "--prefix", "desktop", "ci", "--no-audit", "--no-fund")
        stage = build / "macos-runtime-next"
        remove_generated(stage)
        run(python, "packaging/build_backend.py", "--ffmpeg-dir", decoders,
            "--ffmpeg-notices", decoders / "DECODER_NOTICES.txt", "--output", stage)
        run(python, "packaging/smoke_backend.py", stage / "stemlab-backend", "--require-runtime")
        with (stage / "notices/frontend-sbom.json").open("w") as output:
            subprocess.run(["npm", "--prefix", "desktop", "sbom", "--sbom-format", "cyclonedx"], cwd=ROOT, stdout=output, check=True)
        with (stage / "notices/rust-dependencies.json").open("w") as output:
            subprocess.run(["cargo", "metadata", "--locked", "--manifest-path", "desktop/src-tauri/Cargo.toml",
                            "--format-version", "1", "--filter-platform", "aarch64-apple-darwin"], cwd=ROOT, stdout=output, check=True)
        assets = ROOT / "dist/macos-components"
        run(python, "packaging/prepare_cpu_payload.py", "--runtime", stage, "--platform", "macos-arm64",
            "--archive-output", assets)
        run(stage / "stemlab-backend", "--runtime-probe")
        # Runtime executables/libraries are signed by PyInstaller before hashing.
        # A configured keychain profile also notarizes the independently downloaded ZIP.
        if os.environ.get("STEMLAB_NOTARY_PROFILE"):
            if not os.environ.get("APPLE_SIGNING_IDENTITY"):
                raise ValueError("Runtime notarization requires APPLE_SIGNING_IDENTITY")
            archive = next(assets.glob("*.zip"))
            run("xcrun", "notarytool", "submit", archive, "--keychain-profile",
                os.environ["STEMLAB_NOTARY_PROFILE"], "--wait")
        runtime = ROOT / "desktop/src-tauri/runtime"
        previous = build / "macos-runtime-previous"
        remove_generated(previous)
        if runtime.exists():
            runtime.rename(previous)
        try:
            stage.rename(runtime)
        except OSError:
            if previous.exists() and not runtime.exists():
                previous.rename(runtime)
            raise
        run("npm", "--prefix", "desktop", "run", "tauri", "--", "build", "--target", "aarch64-apple-darwin",
            "--config", "src-tauri/tauri.macos-full.conf.json", "--no-bundle")
        version = json.loads((ROOT / "desktop/package.json").read_text())["version"]
        release = ROOT / "desktop/src-tauri/target/aarch64-apple-darwin/release"
        output = ROOT / "dist/macos"
        output.mkdir(parents=True, exist_ok=True)
        for flavor in (("full", "ondemand") if args.installer == "both" else (args.installer,)):
            remove_generated(release / "runtime")
            bundle_env = dict(os.environ)
            if not bundle_env.get("APPLE_SIGNING_IDENTITY"):
                # Sign the outer ARM64 app ad-hoc for candidates, without
                # passing '-' into PyInstaller's Developer ID signing option.
                bundle_env["APPLE_SIGNING_IDENTITY"] = "-"
            run("npm", "--prefix", "desktop", "run", "tauri", "--", "bundle", "--target", "aarch64-apple-darwin",
                "--config", f"src-tauri/tauri.macos-{flavor}.conf.json", "--bundles", "app,dmg", env=bundle_env)
            candidates = list((release / "bundle/dmg").glob(f"*_{version}_aarch64.dmg"))
            if len(candidates) != 1:
                raise ValueError("Could not identify the generated ARM64 DMG")
            destination = output / f"ViiB-StemLab_{version}_arm64-{flavor}.dmg"
            shutil.copy2(candidates[0], destination)
            inspect_dmg(destination, flavor, build)
            with destination.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            destination.with_suffix(".dmg.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
        remove_generated(previous)
        print("macOS candidates ready. Require physical MPS separation and signing/notarization review before release.")


if __name__ == "__main__":
    main()
