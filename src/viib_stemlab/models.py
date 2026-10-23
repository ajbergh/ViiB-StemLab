from __future__ import annotations

import contextlib
import hashlib
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

# Demucs bag: https://github.com/facebookresearch/demucs/blob/main/demucs/remote/htdemucs_ft.yaml
# Filenames: demucs/remote/files.txt; full hashes verified against the official checkpoint downloads.
FT_CHECKPOINTS = (
    {
        "filename": "f7e0c4bc-ba3fe64a.th",
        "expected_size_bytes": 84141271,
        "sha256": "ba3fe64ae8ef66ac9a4857222ce48efbdc5eb3ad375cb79dd13debee5aaa4066",
        "signature": "f7e0c4bc",
        "sha256_prefix": "ba3fe64a",
        "url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/f7e0c4bc-ba3fe64a.th",
    },
    {
        "filename": "d12395a8-e57c48e6.th",
        "expected_size_bytes": 84141271,
        "sha256": "e57c48e6b0e38af4f7118d7bd08c49f0a0c0edf7d09143bdd902ea0d237303e6",
        "signature": "d12395a8",
        "sha256_prefix": "e57c48e6",
        "url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/d12395a8-e57c48e6.th",
    },
    {
        "filename": "92cfc3b6-ef3bcb9c.th",
        "expected_size_bytes": 84141271,
        "sha256": "ef3bcb9c8b40d14ae5d51b6db2587339cc12c6b77c0be151ce6d69002e087bf2",
        "signature": "92cfc3b6",
        "sha256_prefix": "ef3bcb9c",
        "url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/92cfc3b6-ef3bcb9c.th",
    },
    {
        "filename": "04573f0d-f3cf25b2.th",
        "expected_size_bytes": 84141271,
        "sha256": "f3cf25b222c4eed7cd49dd8b2c9597d50c18bd154090f7b919cfa5f93cf22c49",
        "signature": "04573f0d",
        "sha256_prefix": "f3cf25b2",
        "url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/04573f0d-f3cf25b2.th",
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
        paths = [self.cache_dir / item["filename"] for item in checkpoints]
        cached = all(path.is_file() for path in paths)
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
        return paths[0]

    def _download_checkpoint(
        self, model_name: str, known: dict[str, Any], *, progress: Any = None
    ) -> Path:
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
            shutil.move(str(temp_file), str(final_path))
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
