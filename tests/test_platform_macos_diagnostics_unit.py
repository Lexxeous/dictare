"""macOS dependency checks can be exercised on any CI host."""

import sys
from types import ModuleType

import pytest

from dictare.utils import platform as checks


@pytest.mark.parametrize("installed", [True, False])
def test_mlx_dependency_status(monkeypatch, installed):
    monkeypatch.setattr(checks, "is_macos", lambda: True)
    monkeypatch.setitem(sys.modules, "mlx_whisper", ModuleType("mlx_whisper") if installed else None)
    result = checks._check_stt_deps()[0]
    assert result.name == "mlx-whisper"
    assert result.available is installed
    assert bool(result.install_hint) is not installed


@pytest.mark.parametrize("installed", [True, False])
def test_pynput_dependency_status(monkeypatch, installed):
    monkeypatch.setitem(sys.modules, "pynput", ModuleType("pynput") if installed else None)
    result = checks._check_hotkey_deps_macos()[0]
    assert result.available is installed
    assert bool(result.install_hint) is not installed


@pytest.mark.parametrize("machine,installed,expected", [
    ("arm64", True, "MLX ready"),
    ("arm64", False, "MLX not installed"),
    ("x86_64", False, "Intel Mac"),
])
def test_macos_gpu_diagnostics(monkeypatch, machine, installed, expected):
    import platform

    monkeypatch.setattr(checks, "is_linux", lambda: False)
    monkeypatch.setattr(checks, "is_macos", lambda: True)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    monkeypatch.setitem(sys.modules, "mlx_whisper", ModuleType("mlx_whisper") if installed else None)
    result = checks._check_gpu_deps()[0]
    assert expected in result.message
    assert result.available is installed
