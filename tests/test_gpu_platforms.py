from __future__ import annotations

import sys
import urllib.error
from types import SimpleNamespace

import pytest

from viib_stemlab.cuda_profiles import PROFILES, compatible_profiles
from viib_stemlab.engines.demucs import probe_torch_runtime
from viib_stemlab.errors import InferenceFailedError, MpsOutOfMemoryError, classify_process_failure


@pytest.mark.parametrize("capability", ["7.5", "8.6", "8.9", "12.0"])
def test_rtx_generations_choose_modern_on_current_driver(capability):
    selected = compatible_profiles([{"driver": "610.88", "computeCapability": capability}])
    assert selected[0] == PROFILES["modern"]
    assert (PROFILES["legacy"] in selected) == (capability != "12.0")


def test_older_driver_uses_legacy_and_never_blackwell():
    assert compatible_profiles([{"driver": "560.1", "computeCapability": "8.6"}]) == [PROFILES["legacy"]]
    assert not compatible_profiles([{"driver": "560.1", "computeCapability": "12.0"}])
    assert not compatible_profiles([{"driver": "610.88", "computeCapability": "99.0"}])
    assert compatible_profiles([{"driver": "610.88"}]) == [PROFILES["legacy"]]


def test_mps_execution_and_failure_detection(monkeypatch):
    class Tensor:
        def __mul__(self, value):
            return self

        def sum(self):
            return self

        def item(self):
            return 16

    torch = SimpleNamespace(__version__="2.6.0", version=SimpleNamespace(cuda=None),
                            cuda=SimpleNamespace(is_available=lambda: False),
                            backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)),
                            ones=lambda *a, **kw: Tensor(), mps=SimpleNamespace(synchronize=lambda: None))
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setattr("viib_stemlab.engines.demucs.importlib.util.find_spec", lambda _: object())
    assert probe_torch_runtime().mps_available

    def fail():
        raise RuntimeError("Metal kernel failed")

    torch.mps.synchronize = fail
    runtime = probe_torch_runtime()
    assert not runtime.mps_available
    assert "Metal kernel failed" in runtime.detail


def test_mps_oom_is_specific_and_eligible_for_cpu_retry():
    error = classify_process_failure(1, "RuntimeError: MPS backend out of memory", "mps")
    assert isinstance(error, MpsOutOfMemoryError)
    assert isinstance(error, InferenceFailedError)
    assert error.code == "mps_oom"


# Reuse archive fixtures without requiring NVIDIA hardware.
pytest_plugins = ("test_cuda_runtime",)


@pytest.mark.parametrize("capability,legacy_allowed", [("8.9", True), ("12.0", False)])
def test_unpublished_modern_release_falls_back_only_for_compatible_cards(release, monkeypatch, capability, legacy_allowed):
    from viib_stemlab import cuda_runtime as cuda

    manager, manifest, _ = release
    manager._explicit_manifest = False
    monkeypatch.setattr(cuda, "probe_nvidia", lambda: {"supported": True, "gpus": [
        {"driver": "610.88", "computeCapability": capability}]})
    calls = []

    def fetch(url):
        calls.append(url)
        if url == PROFILES["modern"]["manifestUrl"]:
            raise urllib.error.HTTPError(url, 404, "Not published", {}, None)
        return manifest | {"version": PROFILES["legacy"]["version"]}

    monkeypatch.setattr(manager, "_fetch_manifest", fetch)
    manager._run(True)
    assert bool(manager.worker) == legacy_allowed
    assert len(calls) == (2 if legacy_allowed else 1)


def automatic_modern(manager, monkeypatch):
    from viib_stemlab import cuda_runtime as cuda

    manager._explicit_manifest = False
    monkeypatch.setattr(cuda, "probe_nvidia", lambda: {"supported": True, "gpus": [
        {"driver": "610.88", "computeCapability": "8.9"}]})


@pytest.mark.parametrize("old_version", ["1-torch2.6-cu124", "2-torch2.7.1-cu128"])
def test_old_cached_worker_is_not_activated_and_upgrades_automatically(release, monkeypatch, old_version):
    import json

    manager, manifest, probes = release
    manifest["version"] = old_version
    manager._run(True)
    old_worker = manager.worker
    assert old_worker
    manifest["version"] = PROFILES["modern"]["version"]
    automatic_modern(manager, monkeypatch)
    calls = []
    monkeypatch.setattr(manager, "_fetch_manifest", lambda url: calls.append(url) or manifest)
    # On a fresh launch, offline mode must not activate the incompatible cache.
    from viib_stemlab import cuda_runtime as cuda
    restarted = cuda.CudaRuntimeManager(manager.root)
    automatic_modern(restarted, monkeypatch)
    monkeypatch.setattr(restarted, "_fetch_manifest", lambda url: calls.append(url) or manifest)
    restarted._run(False)
    assert restarted.worker is None
    assert not calls
    assert len(probes) == 1  # No probe/execution of the rejected old worker.
    restarted._run(True)
    assert restarted.status()["ready"], restarted.status()
    assert restarted.worker != old_worker
    assert old_worker.is_file()  # Never replace DLLs that may still be in use.
    assert calls == [PROFILES["modern"]["manifestUrl"]]
    receipt = json.loads((manager.root / "current.json").read_text())
    assert receipt["manifest"]["runtimeVersion"] == PROFILES["modern"]["version"]


@pytest.mark.parametrize("repair", [False, True])
def test_current_worker_reuses_offline_cache_including_repaired_generation(release, monkeypatch, repair):
    from viib_stemlab import cuda_runtime as cuda

    manager, manifest, _ = release
    manifest["version"] = PROFILES["modern"]["version"]
    manager._run(True)
    original = manager.worker
    if repair:
        original.write_bytes(b"corrupt")
        manager._run(True)
        assert manager.worker != original
    restarted = cuda.CudaRuntimeManager(manager.root)
    automatic_modern(restarted, monkeypatch)
    monkeypatch.setattr(restarted, "_fetch_manifest", lambda *_: pytest.fail("Current worker should work offline"))
    restarted._run(True)
    assert restarted.worker == manager.worker
    assert restarted.status()["ready"]


def test_new_release_endpoint_rejects_old_worker_identity(release, monkeypatch):
    manager, manifest, _ = release
    automatic_modern(manager, monkeypatch)
    monkeypatch.setattr(manager, "_fetch_manifest", lambda *_: manifest | {"version": "2-torch2.7.1-cu128"})
    manager._run(True)
    assert manager.worker is None
    assert "does not match" in manager.status()["message"]
