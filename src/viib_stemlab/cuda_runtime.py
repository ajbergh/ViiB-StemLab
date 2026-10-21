"""Optional Windows CUDA worker. The CPU backend never imports its native libraries."""

from __future__ import annotations

import csv
import ctypes
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from viib_stemlab.queue.store import get_default_queue_db_path

WORKER_PROTOCOL = 1
DEFAULT_MANIFEST_URL = (
    "https://github.com/ajbergh/ViiB-StemLab/releases/download/cuda-worker-v1/windows-cuda.json"
)


def worker_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if environment is None else environment)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    # A worker must load its own DLLs, not those from the frozen CPU backend.
    env.pop("_MEIPASS2", None)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        root = Path(sys._MEIPASS).resolve()
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                    if p and not Path(p).resolve().is_relative_to(root))
    return env


_dll_lock = threading.Lock()


def spawn_worker(command: list[str], **kwargs: Any) -> subprocess.Popen:
    """Reset PyInstaller's inherited Windows DLL search path only while spawning."""
    with _dll_lock:
        if os.name != "nt" or not getattr(sys, "frozen", False):
            return subprocess.Popen(command, **kwargs)
        buffer = ctypes.create_unicode_buffer(32768)
        kernel = ctypes.windll.kernel32
        kernel.GetDllDirectoryW(len(buffer), buffer)
        if not kernel.SetDllDirectoryW(None):
            raise OSError("Could not isolate worker DLL search path")
        try:
            return subprocess.Popen(command, **kwargs)
        finally:
            kernel.SetDllDirectoryW(buffer.value or None)


def probe_nvidia() -> dict[str, Any]:
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        return {"supported": False, "gpus": [], "message": "Downloadable CUDA acceleration supports Windows x64."}
    # Use the installed system utility, independent of Torch and user PATH.
    windows = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    candidates = [windows / "System32/nvidia-smi.exe",
                  Path(os.environ.get("PROGRAMW6432", r"C:\Program Files")) / "NVIDIA Corporation/NVSMI/nvidia-smi.exe"]
    executable = next((p for p in candidates if p.is_file()), None)
    if executable is None:
        return {"supported": False, "gpus": [], "message": "No NVIDIA driver detected. CPU processing is available."}
    try:
        result = subprocess.run(
            [str(executable), "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        gpus = [{"name": row[0].strip(), "driver": row[1].strip(), "memoryMb": int(row[2])}
                for row in csv.reader(io.StringIO(result.stdout)) if len(row) == 3]
        return {"supported": bool(gpus), "gpus": gpus,
                "message": "NVIDIA GPU detected." if gpus else "No NVIDIA GPU detected."}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"supported": False, "gpus": [], "message": f"Could not inspect NVIDIA driver: {exc}"}


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_member(name: str) -> Path:
    parts = PurePosixPath(name).parts
    if (not parts or "\\" in name or name.startswith("/")
            or any(p in (".", "..") or ":" in p or p.endswith((".", " "))
                   or re.match(r"(?i)^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)", p)
                   for p in parts)):
        raise ValueError("Unsafe runtime archive path")
    return Path(*parts)


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Invalid CUDA release manifest")
    if value.get("protocol") != WORKER_PROTOCOL or value.get("platform") != "windows-x64":
        raise ValueError("CUDA worker is incompatible with this application")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", str(value.get("version", ""))):
        raise ValueError("Invalid runtime version")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", ""))):
        raise ValueError("Runtime manifest requires a full SHA-256")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(value.get("minimumDriver", ""))):
        raise ValueError("Runtime manifest requires a minimum NVIDIA driver")
    for key in ("size", "unpackedSize"):
        if type(value.get(key)) is not int or not 0 < value[key] <= 12 * 1024**3:
            raise ValueError(f"Invalid runtime {key}")
    if value.get("executable") != "stemlab-backend.exe":
        raise ValueError("Unexpected runtime executable")
    parts = value.get("parts", [value])
    if not isinstance(parts, list) or not 1 <= len(parts) <= 16:
        raise ValueError("Invalid CUDA archive parts")
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("url"), str) or not part["url"].startswith("https://"):
            raise ValueError("CUDA downloads require HTTPS")
        if (type(part.get("size")) is not int or part["size"] <= 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(part.get("sha256", "")))):
            raise ValueError("Invalid CUDA archive part integrity metadata")
    if sum(part["size"] for part in parts) != value["size"]:
        raise ValueError("CUDA archive part sizes do not match")
    return value


def probe_worker(executable: Path, cancel: threading.Event | None = None) -> dict[str, Any]:
    process = spawn_worker(
        [str(executable), "--cuda-probe"], env=worker_environment(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 90
    try:
        while True:
            if cancel and cancel.is_set():
                raise InterruptedError("CUDA setup cancelled. CPU processing remains available.")
            if time.monotonic() > deadline:
                raise TimeoutError("CUDA execution check timed out")
            try:
                output, errors = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                continue
        try:
            value = json.loads(output.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise ValueError(f"CUDA worker could not start: {errors[-1000:]}") from exc
        if process.returncode or value.get("protocol") != WORKER_PROTOCOL or value.get("cudaAvailable") is not True:
            raise ValueError(value.get("detail") or "CUDA execution check failed; check GPU/driver compatibility")
        return value
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


class CudaRuntimeManager:
    def __init__(self, root: Path | None = None, manifest_url: str | None = None) -> None:
        self.root = root or get_default_queue_db_path().parent / "runtimes"
        self.manifest_url = (manifest_url if manifest_url is not None else
                             os.environ.get("VIIB_STEMLAB_CUDA_MANIFEST_URL", DEFAULT_MANIFEST_URL))
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker: Path | None = None
        self._hardware: dict[str, Any] | None = None
        self._state: dict[str, Any] = {"status": "idle", "progress": None,
                                      "message": "CUDA setup has not started."}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {**self._state, "hardware": self._hardware,
                    "configured": bool(self.manifest_url), "ready": self._worker is not None}

    @property
    def worker(self) -> Path | None:
        with self._lock:
            return self._worker

    def _update(self, status: str, message: str, **values: Any) -> None:
        with self._lock:
            self._state.update(status=status, message=message, **values)

    def cancel(self) -> None:
        self._cancel.set()

    def close(self) -> None:
        self.cancel()
        if self._thread:
            self._thread.join(timeout=5)

    def _check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise InterruptedError("CUDA setup cancelled. CPU processing remains available.")

    def start(self, *, download: bool = True) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            if self._worker:
                return
            self._cancel.clear()
            self._update("checking", "Checking NVIDIA acceleration…", progress=None)
            self._thread = threading.Thread(target=self._run, args=(download,), daemon=True,
                                            name="CudaRuntimeSetup")
            self._thread.start()

    def _read_manifest(self) -> dict[str, Any]:
        if not self.manifest_url.startswith("https://"):
            raise ValueError("CUDA manifest requires a trusted HTTPS URL")
        with urllib.request.urlopen(self.manifest_url, timeout=30) as response:
            if not response.geturl().startswith("https://"):
                raise ValueError("Insecure CUDA manifest redirect")
            data = response.read(65537)
        if len(data) > 65536:
            raise ValueError("CUDA manifest is too large")
        return validate_manifest(json.loads(data))

    def _installed(self) -> Path | None:
        receipt = self.root / "current.json"
        self._assert_owned(receipt)
        if not receipt.is_file():
            return None
        value = json.loads(receipt.read_text("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Invalid installed CUDA receipt")
        manifest = validate_manifest(value["manifest"])
        directory = self.root / manifest["version"]
        files = value["files"]
        if not isinstance(files, dict) or manifest["executable"] not in files:
            raise ValueError("Invalid installed CUDA inventory")
        for name, digest in files.items():
            self._check_cancelled()
            path = directory / safe_member(name)
            self._assert_owned(path)
            if path.is_symlink() or not path.is_file() or file_sha256(path) != digest:
                raise ValueError("Installed CUDA files changed; retry setup to repair")
        executable = directory / manifest["executable"]
        self._update("checking", "Testing installed CUDA worker…")
        probe_worker(executable, cancel=self._cancel)
        return executable

    def _assert_owned(self, path: Path) -> None:
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("CUDA runtime path escapes its installation directory")
        for parent in (path, *path.parents):
            if parent.is_symlink() or parent.is_junction():
                raise ValueError("CUDA runtime paths must not be links or junctions")
            if parent == self.root:
                break

    def _run(self, download: bool) -> None:
        try:
            self._hardware = probe_nvidia()
            if not self._hardware["supported"]:
                self._update("unsupported", self._hardware["message"])
                return
            # Only one process may install/verify the per-user runtime at a time.
            self.root.mkdir(parents=True, exist_ok=True)
            self._assert_owned(self.root)
            with (self.root / "setup.lock").open("a+b") as lock:
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    try:
                        executable = self._installed()
                    except InterruptedError:
                        raise
                    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                        executable = None  # Retry replaces an incomplete/incompatible installation.
                    if executable is None and download:
                        if not self.manifest_url:
                            self._update("not_configured", "No CUDA download release is configured. CPU processing is available.")
                            return
                        self._update("checking", "Checking CUDA download release…")
                        self._check_cancelled()
                        manifest = self._read_manifest()
                        driver = tuple(int(p) for p in manifest["minimumDriver"].split("."))
                        if not any(tuple(int(p) for p in gpu["driver"].split(".")) >= driver
                                   for gpu in self._hardware["gpus"]):
                            self._update("incompatible", f"Update the NVIDIA driver to {manifest['minimumDriver']} or newer. CPU processing is available.")
                            return
                        executable = self._install(manifest)
                    self._check_cancelled()
                    if executable:
                        with self._lock:
                            self._worker = executable
                        self._update("ready", "CUDA acceleration is ready. Auto will use your NVIDIA GPU.", progress=1)
                    else:
                        self._update("available", "Automatic CUDA download is disabled. Choose Install to set it up.")
                finally:
                    if os.name == "nt":
                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        except InterruptedError as exc:
            self._update("cancelled", str(exc), progress=None)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                message = (
                    "CUDA download release or file is missing (HTTP 404). "
                    "The app publisher must publish the CUDA worker download assets. "
                    "CPU processing remains available. Retry after the download is published."
                )
            else:
                message = f"CUDA setup unavailable: {exc}. CPU processing remains available."
            self._update("failed", message, progress=None)
        except Exception as exc:
            self._update("failed", f"CUDA setup unavailable: {exc}. CPU processing remains available.", progress=None)

    def _install(self, manifest: dict[str, Any]) -> Path:
        self._check_cancelled()
        if shutil.disk_usage(self.root).free < manifest["size"] + manifest["unpackedSize"] + 256 * 1024**2:
            raise OSError("Insufficient free space for CUDA setup")
        with tempfile.TemporaryDirectory(prefix="cuda-", dir=self.root) as temporary:
            stage = Path(temporary)
            archive = stage / "worker.zip"
            digest = hashlib.sha256()
            downloaded = 0
            self._update("downloading", "Downloading NVIDIA acceleration…", progress=0)
            with archive.open("wb") as out:
                for part in manifest.get("parts", [manifest]):
                    self._check_cancelled()
                    part_hash = hashlib.sha256()
                    part_size = 0
                    with urllib.request.urlopen(part["url"], timeout=30) as response:
                        if not response.geturl().startswith("https://"):
                            raise ValueError("Insecure CUDA archive redirect")
                        while chunk := response.read(1024 * 1024):
                            self._check_cancelled()
                            downloaded += len(chunk)
                            part_size += len(chunk)
                            if part_size > part["size"]:
                                raise ValueError("CUDA archive exceeds declared size")
                            out.write(chunk)
                            digest.update(chunk)
                            part_hash.update(chunk)
                            self._update("downloading", f"Downloading NVIDIA acceleration ({downloaded // 1048576} / {manifest['size'] // 1048576} MB)…",
                                         progress=downloaded / manifest["size"])
                    if part_size != part["size"] or part_hash.hexdigest() != part["sha256"]:
                        raise ValueError("CUDA archive part size/checksum mismatch")
            if downloaded != manifest["size"] or digest.hexdigest() != manifest["sha256"]:
                raise ValueError("CUDA archive size/checksum mismatch")
            self._update("verifying", "Extracting and verifying CUDA worker…", progress=None)
            extracted = stage / "runtime"
            files = {}
            with zipfile.ZipFile(archive) as bundle:
                if len(bundle.infolist()) > 100000 or sum(m.file_size for m in bundle.infolist()) != manifest["unpackedSize"]:
                    raise ValueError("CUDA archive inventory size mismatch")
                names: set[str] = set()
                for member in bundle.infolist():
                    self._check_cancelled()
                    relative = safe_member(member.filename)
                    key = relative.as_posix().casefold()
                    if key in names or stat.S_ISLNK(member.external_attr >> 16):
                        raise ValueError("Duplicate or symbolic runtime archive entry")
                    names.add(key)
                    target = extracted / relative
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as src, target.open("wb") as dst:
                        while chunk := src.read(1024 * 1024):
                            self._check_cancelled()
                            dst.write(chunk)
                    files[relative.as_posix()] = file_sha256(target)
            executable = extracted / manifest["executable"]
            self._update("verifying", "Testing CUDA execution on your GPU…")
            probe_worker(executable, cancel=self._cancel)
            self._check_cancelled()
            destination = self.root / manifest["version"]
            if destination.exists():
                # Do not overwrite a potentially running worker; install a unique generation.
                manifest = {**manifest, "version": f"{manifest['version'][:40]}-{uuid.uuid4().hex[:12]}"}
                destination = self.root / manifest["version"]
            self._assert_owned(destination)
            extracted.rename(destination)
            receipt = stage / "current.json"
            receipt.write_text(json.dumps({"manifest": manifest, "files": files}), encoding="utf-8")
            os.replace(receipt, self.root / "current.json")
            return destination / manifest["executable"]


_manager: CudaRuntimeManager | None = None


def get_cuda_manager() -> CudaRuntimeManager:
    global _manager
    if _manager is None:
        _manager = CudaRuntimeManager()
    return _manager


def get_cuda_worker() -> Path | None:
    """Capability checks do not start setup or instantiate an unneeded manager."""
    return _manager.worker if _manager else None
