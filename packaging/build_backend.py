"""Build a portable backend directory, including decoder binaries and license inventory.

Run with the same Python environment used to install .[demucs,packaging].
Decoder directory must contain standalone ffmpeg/ffprobe binaries and their notices.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg-notices", type=Path, required=True,
                        help="License/source/build information supplied with the decoder distribution")
    parser.add_argument("--output", type=Path, default=ROOT / "desktop" / "src-tauri" / "runtime")
    args = parser.parse_args()
    suffix = ".exe" if os.name == "nt" else ""
    binaries = [args.ffmpeg_dir.resolve() / f"{name}{suffix}" for name in ("ffmpeg", "ffprobe")]
    for binary in binaries:
        if not binary.is_file():
            parser.error(f"Missing decoder binary: {binary}")
        subprocess.run([str(binary), "-version"], check=True, capture_output=True)
    if not args.ffmpeg_notices.is_file():
        parser.error("Decoder notices must be an existing file")
    output = args.output.resolve()
    if output.exists():
        parser.error(f"Remove the previous runtime after inspecting it before rebuilding: {output}")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir",
               "--name", "stemlab-backend", "--paths", str(ROOT / "src"),
               "--distpath", str(ROOT / "build" / "backend-dist"),
               "--workpath", str(ROOT / "build" / "pyinstaller"),
               "--specpath", str(ROOT / "build"),
               "--recursive-copy-metadata", "demucs",
               # htdemucs_ft checkpoints reference this NumPy 1.x pickle path.
               # NumPy 2 exposes it through a compatibility module that the
               # normal PyInstaller NumPy hook does not include.
               "--hidden-import", "numpy.core.multiarray"]
    if sys.platform == "darwin":
        identity = os.environ.get("APPLE_SIGNING_IDENTITY")
        if identity:
            command.extend(["--codesign-identity", identity, "--osx-entitlements-file",
                            str(ROOT / "packaging/macos-entitlements.plist")])
    # Demucs loads model YAML and submodules dynamically. PyInstaller's Torch hook
    # supplies native runtime libraries; torchaudio and soundfile need their data too.
    for package in ("demucs", "torchaudio", "soundfile", "julius", "dora", "einops"):
        command.extend(["--collect-all", package])
    for binary in binaries:
        command.extend(["--add-binary", f"{binary}{os.pathsep}audio-tools"])
    command.append(str(ROOT / "packaging" / "backend_entry.py"))
    subprocess.run(command, check=True, cwd=ROOT)
    shutil.copytree(ROOT / "build" / "backend-dist" / "stemlab-backend", output)
    notices = output / "notices"
    notices.mkdir()
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, notices / "PYTHON_LICENSE.txt")
    shutil.copy2(args.ffmpeg_notices, notices / "DECODER_NOTICES.txt")
    inventory = []
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        inventory.append({"name": name, "version": dist.version,
                          "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                          "home_page": dist.metadata.get("Home-page")})
        for file in dist.files or []:
            if any(word in str(file).lower() for word in ("license", "copying", "notice")):
                if ".dist-info/" not in str(file):
                    continue
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = notices / name / str(file).split(".dist-info/", 1)[-1]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    (notices / "python-environment.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "packaging" / "THIRD_PARTY_NOTICES.md", notices)
    print(f"Backend ready: {output}")


if __name__ == "__main__":
    main()
