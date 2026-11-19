"""Platform diagnostics under simulated hardware and dependency states."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dictare.utils import platform as diagnostics


@pytest.mark.parametrize("exists,ready,message", [(True, True, "Ready"), (True, False, "not usable"), (False, False, "Not installed")])
def test_linux_injection_diagnostics(monkeypatch, exists, ready, message):
    monkeypatch.setattr(diagnostics, "check_command_exists", lambda _: exists)
    monkeypatch.setattr(diagnostics, "check_ydotool_ready", lambda: ready)
    result = diagnostics._check_injection_deps_linux()[0]
    assert result.available is ready
    assert message in result.message


@pytest.mark.parametrize("wayland,x11,message", [(True, False, "Wayland"), (False, True, "X11"), (False, False, "Console")])
def test_display_diagnostics(monkeypatch, wayland, x11, message):
    monkeypatch.setattr(diagnostics, "is_linux", lambda: True)
    monkeypatch.setattr(diagnostics, "is_wayland", lambda: wayland)
    monkeypatch.setattr(diagnostics, "is_x11", lambda: x11)
    assert message in diagnostics._check_display_deps()[0].message


@pytest.mark.parametrize("devices,available,message", [(["keyboard"], True, "Found 1"), ([], False, "No access"), (PermissionError(), False, "Permission denied")])
def test_evdev_diagnostics(monkeypatch, devices, available, message):
    list_devices = MagicMock(side_effect=devices) if isinstance(devices, Exception) else MagicMock(return_value=devices)
    monkeypatch.setitem(sys.modules, "evdev", SimpleNamespace(list_devices=list_devices))
    result = diagnostics._check_hotkey_deps_linux()[1]
    assert result.available is available
    assert message in result.message


@pytest.mark.parametrize("gpu,cudnn,available,message", [(False, None, False, "Not detected"), (True, None, False, "cuDNN missing"), (True, "/lib", True, "cuDNN ready")])
def test_linux_gpu_diagnostics(monkeypatch, gpu, cudnn, available, message):
    monkeypatch.setattr(diagnostics, "is_linux", lambda: True)
    monkeypatch.setattr("dictare.cuda_setup.check_gpu_available", lambda: (gpu, 2))
    monkeypatch.setattr("dictare.cuda_setup._find_cudnn_path", lambda: cudnn)
    result = diagnostics._check_gpu_deps()[0]
    assert result.available is available
    assert message in result.message


@pytest.mark.parametrize("engine,installed", [("say", True), ("espeak", False)])
def test_system_tts_diagnostics(monkeypatch, engine, installed):
    monkeypatch.setattr("dictare.config.load_config", lambda: SimpleNamespace(tts=SimpleNamespace(engine=engine)))
    monkeypatch.setattr(diagnostics, "check_command_exists", lambda _: installed)
    result = diagnostics._check_tts_deps()[0]
    assert result.name == f"TTS ({engine})"
    assert result.available is installed
    assert bool(result.install_hint) is not installed
