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

    def watch_launcher() -> None:
        # A shutdown line or EOF (including launcher crash) stops the backend.
        sys.stdin.readline()
        server.shutdown()

    threading.Thread(target=watch_launcher, daemon=True, name="LauncherLifetime").start()
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}", "token": token}), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        runner.stop_background_worker(cancel_active=True)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
