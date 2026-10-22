"""Build minimal standalone ARM64 decoders from checksum-pinned FFmpeg sources."""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n8.1.2.tar.gz"
SHA256 = "9fd092511605bbebafe095ea6d38d9e40f34d12f7386e1258372df8be0576eb7"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/macos-decoder")
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("Run on native Apple Silicon macOS")
    work = ROOT / "build/macos-decoder-source"
    work.mkdir(parents=True, exist_ok=True)
    archive = work / "ffmpeg.tar.gz"
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        temporary = archive.with_suffix(".partial")
        with urllib.request.urlopen(URL, timeout=60) as source, temporary.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256:
            raise ValueError("FFmpeg source checksum mismatch")
        temporary.replace(archive)
    with tarfile.open(archive) as bundle:
        bundle.extractall(work, filter="data")
    source = work / "FFmpeg-n8.1.2"
    flags = ["--disable-autodetect", "--disable-everything", "--disable-shared", "--enable-static",
             "--disable-doc", "--disable-debug", "--disable-network", "--disable-x86asm",
             "--enable-ffmpeg", "--enable-ffprobe", "--enable-protocol=file",
             "--enable-demuxer=wav,mp3,flac,ogg,mov", "--enable-muxer=wav,flac",
             "--enable-decoder=pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le,mp3,mp3float,flac,vorbis,aac",
             "--enable-parser=mpegaudio,flac,vorbis,aac", "--enable-encoder=pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,flac",
             "--enable-filter=aresample,aformat,anull,atrim,abuffer,abuffersink", "--enable-swresample", "--cc=clang"]
    subprocess.run(["sh", "configure", *flags], cwd=source, check=True)
    subprocess.run(["make", f"-j{min(os.cpu_count() or 2, 8)}"], cwd=source, check=True)
    args.output.mkdir(parents=True, exist_ok=True)
    for tool in ("ffmpeg", "ffprobe"):
        binary = source / tool
        # Fail rather than quietly ship decoders dependent on Homebrew packages.
        linked = subprocess.check_output(["otool", "-L", str(binary)], text=True)
        for line in linked.splitlines()[1:]:
            if not line.strip().startswith(("/usr/lib/", "/System/Library/")):
                raise ValueError(f"Decoder has a non-system dynamic dependency: {line}")
        shutil.copy2(binary, args.output / tool)
    notices = args.output / "DECODER_NOTICES.txt"
    notices.write_text(f"FFmpeg n8.1.2, built from {URL}\nSource SHA-256: {SHA256}\n"
                       + "Configure: " + " ".join(flags) + "\n\n"
                       + (source / "COPYING.LGPLv2.1").read_text(), encoding="utf-8")
    shutil.copy2(archive, args.output / "ffmpeg-source.tar.gz")
    print(f"Self-contained ARM64 decoders and source notices ready: {args.output}")


if __name__ == "__main__":
    main()
