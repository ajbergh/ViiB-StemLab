"""Cancellable stem encoding for WAV, MP3 and Ogg/Vorbis packages."""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from viib_stemlab.cancellation import CancellationToken
from viib_stemlab.errors import StemLabError

ExportEncoder = Callable[[Path, Path, CancellationToken | None], None]


def _soundfile_encoder(output_format: str) -> ExportEncoder | None:
    # Packaged macOS FFmpeg is decode-only; the separator's libsndfile wheel
    # provides these encoders without adding external dynamic libraries.
    try:
        import soundfile as sf

        file_format = "MP3" if output_format == "mp3" else "OGG"
        subtype = "MPEG_LAYER_III" if output_format == "mp3" else "VORBIS"
        if subtype not in sf.available_subtypes(file_format):
            return None
    except (ImportError, OSError, ValueError):
        return None

    def encode(source: Path, destination: Path, token: CancellationToken | None) -> None:
        if token:
            token.raise_if_cancelled()
        try:
            with sf.SoundFile(source) as audio, sf.SoundFile(
                destination, mode="w", samplerate=audio.samplerate, channels=audio.channels,
                format=file_format, subtype=subtype,
            ) as output:
                for block in audio.blocks(blocksize=65536, dtype="float32", always_2d=True):
                    if token:
                        token.raise_if_cancelled()
                    output.write(block)
        except (OSError, RuntimeError, ValueError) as exc:
            raise StemLabError(f"Could not export {destination.name}", code="export_failed",
                               diagnostic=str(exc)) from exc
        if token:
            token.raise_if_cancelled()

    return encode


def validate_output_format(output_format: str) -> None:
    if output_format not in ("wav", "ogg", "mp3"):
        raise ValueError("Choose wav, ogg, or mp3 for output_format")


def prepare_export(output_format: str) -> ExportEncoder | None:
    """Check codec availability before separation and return a cancellable encoder."""
    validate_output_format(output_format)
    if output_format == "wav":
        return None
    try:
        import soundfile  # noqa: F401
    except ImportError as exc:
        raise StemLabError("Compressed stem validation requires SoundFile/libsndfile", code="export_unavailable",
                           diagnostic="Install viib-stemlab[audio] or soundfile>=0.13") from exc
    codec = "libmp3lame" if output_format == "mp3" else "libvorbis"
    ffmpeg = shutil.which("ffmpeg")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    diagnostic = f"Install FFmpeg with the {codec} encoder and ensure it is on PATH."
    if not ffmpeg:
        if fallback := _soundfile_encoder(output_format):
            return fallback
        raise StemLabError("Compressed stem export requires FFmpeg", code="export_unavailable",
                           diagnostic=diagnostic)
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=15, creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if fallback := _soundfile_encoder(output_format):
            return fallback
        raise StemLabError("Could not inspect FFmpeg encoders", code="export_unavailable",
                           diagnostic=diagnostic) from exc
    if result.returncode or not any(
        len(parts := line.split()) > 1 and parts[1] == codec
        for line in result.stdout.splitlines()
    ):
        if fallback := _soundfile_encoder(output_format):
            return fallback
        raise StemLabError(f"FFmpeg cannot export {output_format.upper()} stems",
                           code="export_unavailable", diagnostic=diagnostic)

    def encode(source: Path, destination: Path, token: CancellationToken | None) -> None:
        if token:
            token.raise_if_cancelled()
        quality = ["-q:a", "2" if output_format == "mp3" else "6"]
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-i", str(source), "-map", "0:a:0", "-c:a", codec, *quality, str(destination)]
        try:
            # communicate drains stderr while allowing prompt cancellation without stale callbacks.
            with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, text=True, creationflags=flags) as process:
                try:
                    while True:
                        if token:
                            token.raise_if_cancelled()
                        try:
                            _, stderr = process.communicate(timeout=0.2)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                    if token:
                        token.raise_if_cancelled()
                    if process.returncode or not destination.is_file() or destination.stat().st_size == 0:
                        raise StemLabError(f"Failed to export {destination.name}", code="export_failed",
                                           diagnostic=(stderr or "FFmpeg produced no audio file")[-2000:])
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
        except OSError as exc:
            raise StemLabError(f"Could not export {destination.name}", code="export_failed",
                               diagnostic=str(exc)) from exc

    return encode
