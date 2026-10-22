"""Regenerate synthetic codec interoperability fixtures (FFmpeg + SoundFile)."""
from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import viib_stemlab.package as package_module
from viib_stemlab.constants import CANONICAL_STEMS
from viib_stemlab.exports import _soundfile_encoder

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    original = package_module.prepare_export
    for channels, rate, label in ((1, 22050, "mono"), (2, 44100, "stereo")):
        source = ROOT / "fixtures" / "source" / f"codec-source-{label}.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(channels)
            audio.setsampwidth(2)
            audio.setframerate(rate)
            # Isolated impulses expose codec delay and seek alignment mistakes.
            audio.writeframes(b"".join(
                struct.pack("<h", (24000 if channel == 0 else -18000) if frame in (512, 11025, 40000) else 0)
                for frame in range(44117) for channel in range(channels)
            ))
        for encoder in ("ffmpeg", "soundfile"):
            for output_format in ("mp3", "ogg"):
                package_module.prepare_export = original if encoder == "ffmpeg" else _soundfile_encoder
                package = package_module.build_package_from_stems(
                    source=source, stems={name: source for name in CANONICAL_STEMS},
                    output_root=ROOT / "fixtures", engine_name="synthetic", model_name="impulses",
                    model_version="1", device="cpu", output_format=output_format, overwrite=True,
                )
                target = package.parent / f"package-v1-{output_format}-{label}-{encoder}.viibstems"
                if target.exists():
                    raise FileExistsError(f"Remove the old generated fixture before regenerating: {target}")
                package.rename(target)
                manifest = target / "manifest.json"
                data = json.loads(manifest.read_text())
                data.pop("createdAt", None)
                data.pop("packageId", None)
                manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    package_module.prepare_export = original


if __name__ == "__main__":
    main()
