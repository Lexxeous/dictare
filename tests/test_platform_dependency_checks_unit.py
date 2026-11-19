"""Dependency diagnostics exercise platform and failure paths without hardware."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.utils import platform as checks


def test_runtime_directory_priority(monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(tmp_path / 'missing'))
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    assert checks.get_runtime_dir() == tmp_path
    assert checks.get_socket_dir() == tmp_path / 'dictare'
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(tmp_path))
    assert checks.get_runtime_dir() == tmp_path
    monkeypatch.delenv('XDG_RUNTIME_DIR')
    monkeypatch.delenv('TMPDIR')
    assert str(checks.get_runtime_dir()) == '/tmp'


def test_ydotool_versions_and_daemon_errors(monkeypatch):
    monkeypatch.setattr(checks, 'check_command_exists', lambda cmd: False)
    assert not checks.check_ydotool_ready()
    monkeypatch.setattr(checks, 'check_command_exists', lambda cmd: cmd == 'ydotool')
    monkeypatch.setattr(checks.os, 'access', lambda *args: True)
    assert checks.check_ydotool_ready()
    monkeypatch.setattr(checks, 'check_command_exists', lambda cmd: True)
    monkeypatch.setattr(checks.subprocess, 'run', Mock(return_value=SimpleNamespace(returncode=0)))
    assert checks.check_ydotool_ready()
    monkeypatch.setattr(checks.subprocess, 'run', Mock(side_effect=FileNotFoundError()))
    assert not checks.check_ydotool_ready()


def test_audio_devices_and_error(monkeypatch):
    audio = SimpleNamespace(query_devices=lambda: [{'max_input_channels': 2}, {'max_input_channels': 0}])
    monkeypatch.setitem(sys.modules, 'sounddevice', audio)
    result = checks._check_audio_deps()[0]
    assert result.available and '1 input' in result.message
    audio.query_devices = Mock(side_effect=RuntimeError('no audio'))
    result = checks._check_audio_deps()[0]
    assert not result.available and 'no audio' in result.message


def test_linux_hotkey_device_access(monkeypatch):
    evdev = SimpleNamespace(list_devices=lambda: ['/dev/input/event0'])
    monkeypatch.setitem(sys.modules, 'evdev', evdev)
    assert checks._check_hotkey_deps_linux()[1].available
    evdev.list_devices = Mock(side_effect=PermissionError())
    assert checks._check_hotkey_deps_linux()[1].message == 'Permission denied'
    monkeypatch.setitem(sys.modules, 'evdev', None)
    assert not checks._check_hotkey_deps_linux()[0].available


@pytest.mark.parametrize('exists,ready,message', [(False, False, 'Not installed'), (True, False, 'not usable'), (True, True, 'Ready')])
def test_linux_injection_status(monkeypatch, exists, ready, message):
    monkeypatch.setattr(checks, 'check_command_exists', lambda _: exists)
    monkeypatch.setattr(checks, 'check_ydotool_ready', lambda: ready)
    result = checks._check_injection_deps_linux()[0]
    assert result.available == ready and message in result.message


@pytest.mark.parametrize('gpu,path,available,message', [(False, None, False, 'Not detected'), (True, None, False, 'cuDNN missing'), (True, '/cuda', True, 'cuDNN ready')])
def test_gpu_diagnostics(monkeypatch, gpu, path, available, message):
    import dictare.cuda_setup as cuda
    monkeypatch.setattr(checks, 'is_linux', lambda: True)
    monkeypatch.setattr(cuda, 'check_gpu_available', lambda: (gpu, 1))
    monkeypatch.setattr(cuda, '_find_cudnn_path', lambda: path)
    result = checks._check_gpu_deps()[0]
    assert result.available == available and message in result.message


def test_tts_diagnostics(monkeypatch):
    import dictare.config as config
    import dictare.tts as tts
    current = SimpleNamespace(tts=SimpleNamespace(engine='say'))
    monkeypatch.setattr(config, 'load_config', lambda: current)
    monkeypatch.setattr(checks, 'check_command_exists', lambda _: False)
    assert not checks._check_tts_deps()[0].available
    current.tts.engine = 'example'
    monkeypatch.setattr(tts, 'create_tts_engine', lambda _: SimpleNamespace(is_available=lambda: True))
    assert checks._check_tts_deps()[0].available
    monkeypatch.setattr(tts, 'create_tts_engine', Mock(side_effect=ValueError('missing')))
    assert not checks._check_tts_deps()[0].available
