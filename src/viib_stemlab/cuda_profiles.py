"""Immutable NVIDIA worker profiles shared by selection and release packaging."""
from __future__ import annotations

RELEASE_ROOT = "https://github.com/ajbergh/ViiB-StemLab/releases/download"
PROFILES = {
    "modern": {"torch": "2.7.1", "cuda": "12.8", "flavor": "cu128",
               "version": "5-demucs4.1.0-torch2.7.1-cu128", "minimumDriver": "572.61",
               "capabilities": ["7.5", "8.0", "8.6", "8.9", "9.0", "10.0", "12.0"],
               "manifestUrl": f"{RELEASE_ROOT}/cuda-worker-v5/windows-cuda.json"},
    "legacy": {"torch": "2.6.0", "cuda": "12.4", "flavor": "cu124",
               "version": "6-demucs4.1.0-torch2.6-cu124", "minimumDriver": "551.78",
               "capabilities": ["7.5", "8.0", "8.6", "8.9", "9.0"],
               "manifestUrl": f"{RELEASE_ROOT}/cuda-worker-v6/windows-cuda.json"},
}


def driver_version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def compatible_profiles(gpus: list[dict]) -> list[dict]:
    """Prefer modern kernels; unknown architectures only attempt the proven legacy path."""
    return [profile for name, profile in PROFILES.items() if any(
        driver_version(gpu["driver"]) >= driver_version(profile["minimumDriver"])
        and (gpu.get("computeCapability") in profile["capabilities"]
             or (not gpu.get("computeCapability") and name == "legacy"))
        for gpu in gpus)]
