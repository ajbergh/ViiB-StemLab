"""Private desktop runtime. Stdout contains one connection handshake; stdin owns lifetime."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import threading
from pathlib import Path


def configure_runtime() -> None:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    tools = root / "audio-tools"
    if tools.is_dir():
        os.environ["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")


def main() -> int:
    configure_runtime()
    if sys.argv[1:2] == ["--mps-probe"]:
        from viib_stemlab.engines.demucs import probe_torch_runtime

        runtime = probe_torch_runtime()
        print(json.dumps({"protocol": 1, "mpsAvailable": runtime.mps_available,
                          "torch": runtime.version, "detail": runtime.detail}), flush=True)
        return 0 if runtime.mps_available else 1
    if sys.argv[1:2] == ["--runtime-probe"]:
        import importlib
        import subprocess

        import demucs  # noqa: F401
        import soundfile  # noqa: F401
        import torch
        import torchaudio  # noqa: F401

        # Model checkpoints resolve this legacy NumPy module dynamically while
        # unpickling. Test the frozen import without downloading model weights.
        importlib.import_module("numpy.core.multiarray")
        for tool in ("ffmpeg", "ffprobe"):
            subprocess.run([tool, "-version"], check=True, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        print(json.dumps({"protocol": 1, "available": True, "torch": torch.__version__}), flush=True)
        return 0
    if sys.argv[1:2] == ["--cuda-probe"]:
        import importlib

        import torch

        from viib_stemlab.cuda_runtime import WORKER_PROTOCOL

        try:
            # A CUDA kernel alone does not prove that Demucs checkpoints can
            # unpickle their NumPy scalar values in this frozen runtime.
            importlib.import_module("numpy.core.multiarray")
            # Execute a kernel: detecting a GPU alone does not prove this build
            # supports its architecture or that the installed driver works.
            tensor = torch.ones(8, device="cuda")
            result = (tensor * 2).sum().item()
            torch.cuda.synchronize()
            print(json.dumps({"protocol": WORKER_PROTOCOL, "cudaAvailable": result == 16,
                              "modelCheckpointCompatible": True,
                              "torch": torch.__version__, "cuda": torch.version.cuda,
                              "gpu": torch.cuda.get_device_name(0)}), flush=True)
            return 0
        except Exception as exc:
            print(json.dumps({"protocol": WORKER_PROTOCOL, "cudaAvailable": False,
                              "detail": str(exc)}), flush=True)
            return 1
    if sys.argv[1:2] == ["--demucs-worker"]:
        from demucs.separate import main as separate

        separate(sys.argv[2:])
        return 0

    from viib_stemlab.queue.runner import QueueRunner
    from viib_stemlab.queue.store import QueueStore, get_default_queue_db_path
    from viib_stemlab.ui.server import StemLabHTTPServer

    app_dir = get_default_queue_db_path().parent
    app_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=app_dir / "desktop.log", level=logging.INFO)
    os.environ.setdefault("TORCH_HOME", str(app_dir / "torch"))
    # Load native Torch/NumPy libraries on the main thread. Deferring their first
    # import to a ThreadingHTTPServer request can deadlock Windows' DLL loader
    # in a frozen runtime. The readiness handshake follows initialization.
    from viib_stemlab.engines.demucs import probe_torch_runtime

    runtime = probe_torch_runtime()
    logging.info("Native runtime initialized: available=%s, detail=%s", runtime.available, runtime.detail)
    store = QueueStore()
    store.recover_interrupted_jobs()
    runner = QueueRunner(store)
    token = secrets.token_urlsafe(32)
    server = StemLabHTTPServer(("127.0.0.1", 0), store, runner, session_token=token)
    if not runtime.cuda_available:
        server.prepare_cuda()

    def watch_launcher() -> None:
        # A shutdown line or EOF (including launcher crash) stops the backend.
        sys.stdin.readline()
        server.shutdown()

    threading.Thread(target=watch_launcher, daemon=True, name="LauncherLifetime").start()
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}", "token": token}), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.cuda.close()
        runner.stop_background_worker(cancel_active=True)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
