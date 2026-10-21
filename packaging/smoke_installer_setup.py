"""Test native Full/offline and On-demand/HTTPS setup with real release payloads.

Requires Rust and OpenSSL on the build machine; no certificates are installed in
the OS trust store. Nothing is published. The native test trusts only this fixture.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openssl", default=shutil.which("openssl") or "C:/Program Files/Git/usr/bin/openssl.exe")
    args = parser.parse_args()
    release = json.loads((ROOT / "dist/components/windows-cpu.json").read_text("utf-8"))
    with tempfile.TemporaryDirectory(prefix="installer-https-", dir=ROOT / "build") as temporary:
        work = Path(temporary)
        cert, key = work / "cert.pem", work / "key.pem"
        subprocess.run([args.openssl, "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-keyout", str(key),
                        "-out", str(cert), "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                       check=True, capture_output=True)

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                if self.path in ("/windows-cpu.json", "/bad-sha.json"):
                    value = release if self.path == "/windows-cpu.json" else release | {"sha256": "0" * 64}
                    body = json.dumps(value).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    super().do_GET()

        server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(ROOT / "dist/components")))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        endpoint = f"https://127.0.0.1:{server.server_port}"
        release["url"] = endpoint + "/" + release["url"].rsplit("/", 1)[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = dict(os.environ, VIIB_TEST_FULL_RESOURCES=str(ROOT / "desktop/src-tauri"),
                   VIIB_TEST_CPU_MANIFEST=endpoint + "/windows-cpu.json", VIIB_STEMLAB_SETUP_CA_CERT=str(cert))
        env.pop("VIIB_STEMLAB_CPU_MANIFEST_URL", None)
        try:
            subprocess.run(["cargo", "test", "--locked", "--manifest-path", str(ROOT / "desktop/src-tauri/Cargo.toml"),
                            "real_full_and_ondemand_payloads", "--", "--ignored", "--nocapture"], check=True, env=env)
        finally:
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()


if __name__ == "__main__":
    main()
