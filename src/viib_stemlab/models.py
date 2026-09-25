from __future__ import annotations

import os
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from viib_stemlab.errors import ModelDownloadError, ModelMissingError
from viib_stemlab.progress import ProgressEmitter

KNOWN_MODELS: dict[str, dict[str, Any]] = {
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

    def get_model_info(self, model_name: str) -> ModelCacheInfo:
        known = KNOWN_MODELS.get(model_name)
        if known:
            filename = known["filename"]
            sig = known["signature"]
            url = known["url"]
            expected_size = known.get("expected_size_bytes")
        else:
            filename = f"{model_name}.th"
            sig = model_name
            url = ""
            expected_size = None

        candidate = self.cache_dir / filename
        if candidate.is_file():
            size = candidate.stat().st_size
            return ModelCacheInfo(
                name=model_name,
                signature=sig,
                filename=filename,
                url=url,
                cached=True,
                local_path=candidate,
                size_bytes=size,
                expected_size_bytes=expected_size,
            )

        return ModelCacheInfo(
            name=model_name,
            signature=sig,
            filename=filename,
            url=url,
            cached=False,
            local_path=None,
            size_bytes=None,
            expected_size_bytes=expected_size,
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
        emitter.emit("preflight", None, f"Model '{model_name}' not in cache; downloading weights...")
        self.download_model(model_name, progress=progress)
        return self.get_model_info(model_name)

    def download_model(self, model_name: str, *, progress: Any = None) -> Path:
        """Download model weights with atomic writing and progress reporting."""
        known = KNOWN_MODELS.get(model_name)
        if not known:
            raise ModelMissingError(f"Cannot download unknown model '{model_name}'")

        url = known["url"]
        filename = known["filename"]
        expected_size = known.get("expected_size_bytes")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.cache_dir / filename
        if final_path.is_file():
            return final_path

        emitter = ProgressEmitter(progress)
        emitter.emit("preflight", 0.0, f"Downloading {filename}...")

        temp_fd, temp_path_str = tempfile.mkstemp(
            prefix=f".{filename}.",
            suffix=".partial",
            dir=self.cache_dir,
        )
        temp_file = Path(temp_path_str)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ViiB-StemLab/1.0"},
            )
            with os.fdopen(temp_fd, "wb") as out_fp:
                with urllib.request.urlopen(req, timeout=30.0) as response:
                    total_bytes = int(
                        response.headers.get("Content-Length") or expected_size or 0
                    )
                    downloaded = 0
                    chunk_size = 64 * 1024

                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_fp.write(chunk)
                        downloaded += len(chunk)
                        if total_bytes > 0:
                            pct = min(1.0, downloaded / total_bytes)
                            emitter.emit(
                                "preflight",
                                pct,
                                f"Downloading {model_name} weights ({downloaded // 1048576}MB / {total_bytes // 1048576}MB)",
                            )

            # Atomic move into final position
            shutil.move(str(temp_file), str(final_path))
            emitter.emit("preflight", 1.0, f"Model {model_name} downloaded successfully")
            return final_path
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise ModelDownloadError(
                f"Failed to download model weights for '{model_name}' from {url}: {exc}",
                details={"model": model_name, "url": url, "error": str(exc)},
            ) from exc
