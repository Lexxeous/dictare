"""Hardware probing without loading native GPU libraries or executing sysctl."""

import ctypes
import subprocess
import sys
from types import SimpleNamespace

import pytest

from dictare.utils import hardware


def test_cuda_library_setup_preloads_existing_libraries_and_preserves_path(tmp_path, monkeypatch):
    root = tmp_path / "nvidia"
    cudnn = root / "cudnn" / "lib"
    cublas = root / "cublas" / "lib"
    cudnn.mkdir(parents=True)
    cublas.mkdir(parents=True)
    (cudnn / "libcudnn.so.9").touch()
    (cublas / "libcublas.so.12").touch()
    loaded = []
    monkeypatch.setattr(sys, "path", [str(tmp_path)])
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing")
    monkeypatch.setattr(ctypes, "CDLL", lambda path, mode: loaded.append((path, mode)))

    hardware.setup_cuda_library_path()

    assert loaded == [
        (str(cudnn / "libcudnn.so.9"), ctypes.RTLD_GLOBAL),
        (str(cublas / "libcublas.so.12"), ctypes.RTLD_GLOBAL),
    ]
    assert hardware.os.environ["LD_LIBRARY_PATH"] == f"{cudnn}:{cublas}:/existing"


def test_cuda_library_setup_tolerates_loader_error(tmp_path, monkeypatch):
    lib = tmp_path / "nvidia" / "cudnn" / "lib"
    lib.mkdir(parents=True)
    (lib / "libcudnn.so.9").touch()
    monkeypatch.setattr(sys, "path", [str(tmp_path)])
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    def fail(*args, **kwargs):
        raise OSError("unavailable")
    monkeypatch.setattr(ctypes, "CDLL", fail)
    hardware.setup_cuda_library_path()
    assert hardware.os.environ["LD_LIBRARY_PATH"] == str(lib)


@pytest.mark.parametrize(
    ("outputs", "expected"),
    [
        (["QEMU virtual CPU"], True),
        (["Apple M1", "VirtualMac2,1"], True),
        (["Apple M1", "MacBookPro", "vmm", "AppleVirtualPlatform"], True),
        (["Apple M1", "MacBookPro", "", ""], False),
    ],
)
def test_macos_vm_detection_uses_hardware_indicators(monkeypatch, outputs, expected):
    monkeypatch.setattr(sys, "platform", "darwin")
    results = iter(outputs)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=next(results)))
    assert hardware.is_virtualized_macos() is expected


def test_macos_vm_detection_handles_missing_tool(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    def fail(*args, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(subprocess, "run", fail)
    assert not hardware.is_virtualized_macos()
