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
