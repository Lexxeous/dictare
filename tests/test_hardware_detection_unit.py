"""Test hardware decisions with simulated devices and commands."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.utils import hardware


def test_nvidia_detection(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=b"GPU"))
    monkeypatch.setattr(subprocess, "run", run)
    assert hardware.detect_nvidia_gpu() == "found"
    run.return_value.stdout = b""
    assert hardware.detect_nvidia_gpu() == "none"
    run.side_effect = FileNotFoundError()
    assert hardware.detect_nvidia_gpu() == "no_tool"
    run.side_effect = subprocess.TimeoutExpired("nvidia-smi", 3)
    assert hardware.detect_nvidia_gpu() == "none"


@pytest.mark.parametrize("outputs,expected", [
    (["QEMU virtual CPU"], True),
    (["Apple CPU", "VirtualMac"], True),
    (["Apple CPU", "MacBook", "VMM", "AppleVirtualPlatform"], True),
    (["Apple CPU", "MacBook", "", ""], False),
])
def test_virtual_machine_detection(monkeypatch, outputs, expected):
    monkeypatch.setattr(hardware.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=[SimpleNamespace(stdout=output) for output in outputs]))
    assert hardware.is_virtualized_macos() is expected


@pytest.mark.parametrize("mode,device,compute,enabled", [
    ("cpu", "cpu", "int8", True),
    ("vm", "cpu", "int8", False),
    ("mlx", "mlx", "default", True),
    ("cuda", "cuda", "float16", True),
    ("none", "cpu", "default", True),
])
def test_acceleration_selection(monkeypatch, mode, device, compute, enabled):
    config = SimpleNamespace(stt=SimpleNamespace(advanced=SimpleNamespace(device="auto", compute_type="default"), hw_accel=True))
    monkeypatch.setattr(hardware, "is_virtualized_macos", lambda: mode == "vm")
    monkeypatch.setattr(hardware, "is_mlx_available", lambda: mode == "mlx")
    monkeypatch.setattr(hardware, "is_cuda_available", lambda: mode == "cuda")
    setup = Mock()
    monkeypatch.setattr(hardware, "setup_cuda_library_path", setup)
    monkeypatch.setattr(hardware.sys, "platform", "darwin")
    hardware.auto_detect_acceleration(config, cpu_only=mode == "cpu", console=Mock())
    assert (config.stt.advanced.device, config.stt.advanced.compute_type, config.stt.hw_accel) == (device, compute, enabled)
    assert setup.called == (mode == "cuda")
