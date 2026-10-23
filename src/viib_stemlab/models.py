from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from viib_stemlab.errors import ModelDownloadError, ModelMissingError
from viib_stemlab.progress import ProgressEmitter

_DOWNLOAD_LOCK = threading.RLock()

# Official Demucs 4.1 safetensors bundle, pinned independently of mutable hub refs.
FT_REVISION = "d74ac89c3a1e874fc78f152555cf4d8533f06cd4"
FT_HUB_REPO = "models--adefossez--HTDemucs-ft"
FT_CHECKPOINTS = (
    {
        "filename": "htdemucs_ft.yaml",
        "signature": "htdemucs_ft",
        "expected_size_bytes": 149,
        "sha256": "69470b8c1bbd674437b51bc9fb491327a10ab0396b702c93389b9cf750016346",
        "url": "https://huggingface.co/adefossez/HTDemucs-ft/resolve/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/htdemucs_ft.yaml",
        "cache_path": "huggingface/models--adefossez--HTDemucs-ft/snapshots/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/htdemucs_ft.yaml",
    },
    {
        "filename": "f7e0c4bc.safetensors",
        "signature": "f7e0c4bc",
        "expected_size_bytes": 84025440,
        "sha256": "2c85ab3c62dd6edd8e0b965e38b16fd1cdde357cc25de6b6bc9ce7c83f60925f",
        "url": "https://huggingface.co/adefossez/HTDemucs-ft/resolve/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/f7e0c4bc.safetensors",
        "cache_path": "huggingface/models--adefossez--HTDemucs-ft/snapshots/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/f7e0c4bc.safetensors",
    },
    {
        "filename": "d12395a8.safetensors",
        "signature": "d12395a8",
        "expected_size_bytes": 84025440,
        "sha256": "5b01a97567ae9a3178a6236fb520251045c03eb8834bc8c24a4eec11d6c8fb56",
        "url": "https://huggingface.co/adefossez/HTDemucs-ft/resolve/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/d12395a8.safetensors",
        "cache_path": "huggingface/models--adefossez--HTDemucs-ft/snapshots/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/d12395a8.safetensors",
    },
    {
        "filename": "92cfc3b6.safetensors",
        "signature": "92cfc3b6",
        "expected_size_bytes": 84025440,
        "sha256": "a241863551f30d01c42bd7b97da40839922ead3acb0f1fcab25682f55b4eeb59",
        "url": "https://huggingface.co/adefossez/HTDemucs-ft/resolve/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/92cfc3b6.safetensors",
        "cache_path": "huggingface/models--adefossez--HTDemucs-ft/snapshots/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/92cfc3b6.safetensors",
    },
    {
        "filename": "04573f0d.safetensors",
        "signature": "04573f0d",
        "expected_size_bytes": 84025440,
        "sha256": "68854b0d7c2b3274723b5761f6fd9f5aec5f1bcd3f0de7c1669546fdb7871b7c",
        "url": "https://huggingface.co/adefossez/HTDemucs-ft/resolve/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/04573f0d.safetensors",
        "cache_path": "huggingface/models--adefossez--HTDemucs-ft/snapshots/d74ac89c3a1e874fc78f152555cf4d8533f06cd4/04573f0d.safetensors",
    },
)


KNOWN_MODELS: dict[str, dict[str, Any]] = {
    "htdemucs_ft": {"checkpoints": FT_CHECKPOINTS},
    "htdemucs_6s": {
        "signature": "5c90dfd2",
        "filename": "5c90dfd2-34c22ccb.th",
        "expected_size_bytes": 54996327,
        "sha256_prefix": "34c22ccb",
        "url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/5c90dfd2-34c22ccb.th",
    },
    "htdemucs": {
        "signature": "95574cff",
        "filename": "95574cff-8735e17b.th",
        "expected_size_bytes": 84196143,
        "sha256_prefix": "8735e17b",
        "url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/95574cff-8735e17b.th",
    },
}


@dataclass(frozen=True)
class ModelCacheInfo:
    name: str
    signature: str
    filename: str
    url: str
    cached: bool
    local_path: Path | None
    size_bytes: int | None
    expected_size_bytes: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "signature": self.signature,
            "filename": self.filename,
            "url": self.url,
            "cached": self.cached,
            "localPath": str(self.local_path) if self.local_path else None,
            "sizeBytes": self.size_bytes,
            "expectedSizeBytes": self.expected_size_bytes,
        }


class ModelCacheManager:
    """Manages model weight inspection, cache directory resolution, and preflight downloading."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = self.resolve_checkpoints_dir(cache_dir)

    @classmethod
    def resolve_checkpoints_dir(cls, explicit: Path | None = None) -> Path:
        """Resolve the directory where model checkpoint weights are stored."""
        if explicit is not None:
            # If user points directly to checkpoints dir or its parent
            p = Path(explicit)
            if p.name == "checkpoints":
                return p
            return p / "checkpoints" if (p / "checkpoints").exists() else p

        env_viib = os.environ.get("VIIB_STEMLAB_CACHE_DIR")
        if env_viib:
            p = Path(env_viib)
            return p / "checkpoints" if (p / "checkpoints").exists() else p

        env_torch = os.environ.get("TORCH_HOME")
        if env_torch:
            return Path(env_torch) / "hub" / "checkpoints"

        # Try torch.hub if available
        try:
            import torch.hub

            return Path(torch.hub.get_dir()) / "checkpoints"
        except Exception:
            return Path.home() / ".cache" / "torch" / "hub" / "checkpoints"

    def get_torch_home(self) -> Path:
        """Calculate the TORCH_HOME directory corresponding to the active cache directory."""
        # If cache_dir ends in hub/checkpoints, go up 2 levels
        if self.cache_dir.name == "checkpoints" and self.cache_dir.parent.name == "hub":
            return self.cache_dir.parent.parent
        # Otherwise the cache_dir itself can serve as root with a hub/checkpoints symlink/subfolder
        return self.cache_dir

    def get_hf_cache(self) -> Path:
        return self.cache_dir / "huggingface"

    @staticmethod
    def _checkpoint_valid(path: Path, item: dict[str, Any]) -> bool:
        if not path.is_file():
            return False
        if "cache_path" not in item:  # Explicit legacy model compatibility.
            return True
        if path.stat().st_size != item["expected_size_bytes"]:
            return False
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"]

    def write_hf_reference(self) -> None:
        ref = self.get_hf_cache() / FT_HUB_REPO / "refs/main"
        ref.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=ref.parent, suffix=".partial")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(FT_REVISION)
            os.replace(name, ref)
        finally:
            Path(name).unlink(missing_ok=True)

    def get_model_info(self, model_name: str) -> ModelCacheInfo:
        known = KNOWN_MODELS.get(model_name)
        checkpoints = (
            known.get("checkpoints", (known,))
            if known
            else (
                {
                    "filename": f"{model_name}.th",
                    "signature": model_name,
                    "url": "",
                },
            )
        )
        paths = [self.cache_dir / item.get("cache_path", item["filename"]) for item in checkpoints]
        cached = all(
            self._checkpoint_valid(path, item)
            for path, item in zip(paths, checkpoints, strict=True)
        )
        if model_name == "htdemucs_ft":
            ref = self.cache_dir / "huggingface" / FT_HUB_REPO / "refs/main"
            cached = cached and ref.is_file() and ref.read_text().strip() == FT_REVISION
        sizes = [item.get("expected_size_bytes") for item in checkpoints]
        return ModelCacheInfo(
            name=model_name,
            signature=",".join(item["signature"] for item in checkpoints),
            filename=",".join(item["filename"] for item in checkpoints),
            url=",".join(item["url"] for item in checkpoints),
            cached=cached,
            local_path=paths[0] if cached else None,
            size_bytes=sum(path.stat().st_size for path in paths) if cached else None,
            expected_size_bytes=sum(sizes) if all(size is not None for size in sizes) else None,
        )

    def is_model_cached(self, model_name: str) -> bool:
        return self.get_model_info(model_name).cached

    def list_known_models(self) -> list[ModelCacheInfo]:
        return [self.get_model_info(name) for name in sorted(KNOWN_MODELS)]

    def preflight_model(
        self,
        model_name: str,
        *,
        allow_download: bool = True,
        progress: Any = None,
    ) -> ModelCacheInfo:
        """Verify model weight availability before generation starts."""
        info = self.get_model_info(model_name)
        if info.cached:
            return info

        if not allow_download:
            raise ModelMissingError(
                f"Model weights for '{model_name}' are not present in cache ({self.cache_dir}) and downloading is disabled.",
                details={"model": model_name, "cache_dir": str(self.cache_dir)},
            )

        if not info.url:
            raise ModelMissingError(
                f"Model '{model_name}' is not cached and has no known remote download URL.",
                details={"model": model_name},
            )

        emitter = ProgressEmitter(progress)
        emitter.emit(
            "preflight", None, f"Model '{model_name}' not in cache; downloading weights..."
        )
        self.download_model(model_name, progress=progress)
        return self.get_model_info(model_name)

    def download_model(self, model_name: str, *, progress: Any = None) -> Path:
        """Serialize first-use downloads shared by concurrent songs and the UI."""
        with _DOWNLOAD_LOCK:
            return self._download_model(model_name, progress=progress)

    def _download_model(self, model_name: str, *, progress: Any = None) -> Path:
        """Download model weights with atomic writing and progress reporting."""
        known = KNOWN_MODELS.get(model_name)
        if not known:
            raise ModelMissingError(f"Cannot download unknown model '{model_name}'")

        checkpoints = known.get("checkpoints", (known,))
        emitter = ProgressEmitter(progress)
        paths = []
        for index, checkpoint in enumerate(checkpoints):

            def report(stage, value, message, *, index=index):
                emitter.emit(stage, (index + (value or 0.0)) / len(checkpoints), message)

            paths.append(self._download_checkpoint(model_name, checkpoint, progress=report))
        if model_name == "htdemucs_ft":
            self.write_hf_reference()
        return paths[0]

    def _download_checkpoint(
        self, model_name: str, known: dict[str, Any], *, progress: Any = None
    ) -> Path:
        url = known["url"]
        filename = known["filename"]
        expected_size = known.get("expected_size_bytes")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.cache_dir / known.get("cache_path", filename)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if self._checkpoint_valid(final_path, known):
            return final_path

        emitter = ProgressEmitter(progress)
        emitter.emit("preflight", 0.0, f"Downloading {filename}...")

        temp_fd, temp_path_str = tempfile.mkstemp(
            prefix=f".{filename}.",
            suffix=".partial",
            dir=final_path.parent,
        )
        temp_file = Path(temp_path_str)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ViiB-StemLab/1.0"},
            )
            with (
                os.fdopen(temp_fd, "wb") as out_fp,
                urllib.request.urlopen(req, timeout=30.0) as response,
            ):
                total_bytes = int(response.headers.get("Content-Length") or expected_size or 0)
                downloaded = 0
                digest = hashlib.sha256()
                chunk_size = 64 * 1024

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_fp.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if total_bytes > 0:
                        pct = min(1.0, downloaded / total_bytes)
                        emitter.emit(
                            "preflight",
                            pct,
                            f"Downloading {model_name} weights ({downloaded // 1048576}MB / {total_bytes // 1048576}MB)",
                        )

            if total_bytes and downloaded != total_bytes:
                raise OSError(f"Incomplete model download: {downloaded} of {total_bytes} bytes")
            if known.get("sha256") and digest.hexdigest() != known["sha256"]:
                raise OSError("Model checksum mismatch; retry the download")
            prefix = known.get("sha256_prefix")
            if prefix and not digest.hexdigest().startswith(prefix):
                raise OSError("Model checksum mismatch; retry the download")
            if expected_size and downloaded != expected_size:
                raise OSError("Model weight size mismatch; retry the download")
            # Atomic move into final position only after validating the download.
            os.replace(temp_file, final_path)
            emitter.emit("preflight", 1.0, f"Model {model_name} downloaded successfully")
            return final_path
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            if temp_file.exists():
                with contextlib.suppress(OSError):
                    temp_file.unlink()
            raise ModelDownloadError(
                f"Failed to download model weights for '{model_name}' from {url}: {exc}",
                details={"model": model_name, "url": url, "error": str(exc)},
            ) from exc
