"""Exercise a real packaged backend: handshake, authentication, settings, doctor and EOF exit."""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, nargs="?")
    parser.add_argument("--source", action="store_true", help="Exercise the backend in the current Python environment")
    parser.add_argument("--require-runtime", action="store_true")
    parser.add_argument("--model-cache-dir", type=Path, help="Verified managed model cache for offline model and separation checks")
    parser.add_argument("--separate", action="store_true", help="Downloads weights and processes a short synthetic track")
    parser.add_argument("--format", choices=("wav", "mp3", "ogg", "flac"), default="wav")
    parser.add_argument("--device", choices=("cpu", "cuda", "mps"), default="cpu")
    args = parser.parse_args()
    if not args.source and args.executable is None:
        parser.error("Provide a bundled executable or --source")
    command = [sys.executable, "-m", "viib_stemlab.desktop_backend"] if args.source else [str(args.executable.resolve())]
    with tempfile.TemporaryDirectory(prefix="stemlab-smoke-") as state_dir:
        env = dict(os.environ, VIIB_STEMLAB_HOME=state_dir)
        # Packaging smoke must not download a separate acceleration runtime.
        env["VIIB_STEMLAB_CUDA_MANIFEST_URL"] = ""
        # Keep this smoke independent from developer machine overrides and caches.
        for key in ("VIIB_STEMLAB_QUEUE_DB", "VIIB_STEMLAB_CACHE_DIR", "TORCH_HOME"):
            env.pop(key, None)
        if args.model_cache_dir:
            cache = Path(state_dir) / "torch/hub/checkpoints"
            shutil.copytree(args.model_cache_dir, cache)
            env["TORCH_HOME"] = str(Path(state_dir) / "torch")
            env["HF_HUB_OFFLINE"] = "1"
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=errors, text=True, env=env)
            try:
                handshake: queue.Queue[str] = queue.Queue()
                threading.Thread(target=lambda: handshake.put(process.stdout.readline()), daemon=True).start()
                connection = json.loads(handshake.get(timeout=60))
                print("Backend readiness handshake passed", flush=True)
                base = connection["url"]

                def request(path: str, data: dict | None = None) -> dict:
                    req = urllib.request.Request(base + path,
                        data=json.dumps(data).encode() if data is not None else None,
                        headers={"Authorization": f"Bearer {connection['token']}", "Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=60) as response:
                        return json.load(response)

                try:
                    urllib.request.urlopen(base + "/api/queue", timeout=10)
                    raise AssertionError("Backend accepted a request without its session secret")
                except urllib.error.HTTPError as exc:
                    assert exc.code == 401
                assert request("/api/health")["status"] == "ok"
                prefs = request("/api/settings", {"device": args.device, "fallback_to_cpu": False})
                assert prefs["model"] == "htdemucs_ft"
                assert request("/api/settings")["device"] == args.device
                assert request("/api/queue")["counts"]["total"] == 0
                print("Private API and preference checks passed", flush=True)
                if args.require_runtime:
                    runtime = subprocess.run([*command, "--runtime-probe", *(["--check-model"] if args.model_cache_dir else [])],
                                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, env=env)
                    assert runtime.returncode == 0, runtime.stderr
                    assert json.loads(runtime.stdout)["available"], runtime.stdout
                    assert json.loads(runtime.stdout)["demucs"] == "4.1.0", runtime.stdout
                    doctor = request("/api/doctor")
                    assert doctor["torch"]["available"], doctor
                    assert doctor["demucs"]["available"], doctor
                    assert doctor["input"]["ffmpegAvailable"], doctor
                    assert doctor["input"]["ffprobeAvailable"], doctor
                    print("Bundled engine and decoder diagnostics passed", flush=True)
                    worker = subprocess.run([*command, "--demucs-worker", "--help"],
                                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, env=env)
                    assert worker.returncode == 0, worker.stderr
                    print("Demucs worker startup passed", flush=True)
                if args.separate:
                    audio = Path(state_dir) / "smoke.wav"
                    with wave.open(str(audio), "wb") as writer:
                        writer.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
                        for frame in range(44100 * 3):
                            value = int(9000 * math.sin(2 * math.pi * 220 * frame / 44100))
                            writer.writeframesraw(struct.pack("<hh", value, value))
                    if args.format != "wav":
                        decoder = shutil.which("ffmpeg") if args.source else str(
                            args.executable.resolve().parent / "_internal" / "audio-tools" /
                            ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
                        )
                        converted = audio.with_suffix(f".{args.format}")
                        subprocess.run([decoder, "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio), str(converted)], check=True, timeout=30)
                        audio = converted
                    added = request("/api/queue/add", {"paths": [str(audio)], "device": args.device,
                        "fallback_to_cpu": False, "output_library": str(Path(state_dir) / "output")})
                    assert added["added_count"] == 1, added
                    request("/api/queue/start", {})
                    print(f"Running short packaged {args.device} separation (model download may be required)", flush=True)
                    deadline = time.monotonic() + 600
                    while time.monotonic() < deadline:
                        job = request("/api/queue")["jobs"][0]
                        if job["status"] == "complete":
                            result = request("/api/package/validate", {"package_path": job["package_path"], "source_path": str(audio)})
                            assert result["valid"], result
                            assert job["actual_device"] == args.device, job
                            manifest = json.loads((Path(job["package_path"]) / "manifest.json").read_text("utf-8"))
                            assert manifest["model"]["device"] == args.device, manifest
                            assert manifest["model"]["name"] == "htdemucs_ft", manifest
                            assert manifest["model"]["version"] == "4.1.0", manifest
                            assert manifest["stemLayout"] == "four", manifest
                            assert set(manifest["stems"]) == {"vocals", "drums", "bass", "other"}, manifest
                            print("Packaged four-stem generation and validation passed", flush=True)
                            break
                        assert job["status"] not in ("failed", "cancelled"), job
                        time.sleep(1)
                    else:
                        raise AssertionError("Packaged separation exceeded 10 minutes")
                process.stdin.close()
                assert process.wait(timeout=25) == 0
                assert (Path(state_dir) / "settings.json").is_file()
                print("Packaged backend smoke passed")
            except BaseException:
                errors.seek(0)
                print(errors.read())
                raise
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
