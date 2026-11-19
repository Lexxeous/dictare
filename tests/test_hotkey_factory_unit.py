"""Backend selection and fallback without opening input devices."""
import sys
from types import ModuleType, SimpleNamespace

import pytest

from dictare.hotkey import factory


def module_with(monkeypatch, name, attribute, value):
    module = ModuleType(name)
    setattr(module, attribute, value)
    monkeypatch.setitem(sys.modules, name, module)


def test_linux_uses_suggested_key(monkeypatch):
    monkeypatch.setattr(factory.sys, 'platform', 'linux')
    class Evdev:
        def __init__(self, key, **kwargs):
            self.key, self.kwargs = key, kwargs
        def is_key_available(self):
            return False
        @staticmethod
        def suggest_fallback_key():
            return 'f9'
    module_with(monkeypatch, 'dictare.hotkey.evdev_listener', 'EvdevHotkeyListener', Evdev)
    result = factory.create_hotkey_listener(SimpleNamespace(key='f8', device='keyboard', mode_switch_modifier='ctrl'))
    assert result.key == 'f9'
    assert result.kwargs == {'target_device': 'keyboard', 'mode_switch_modifier': 'ctrl'}


def test_linux_error_falls_back_to_pynput(monkeypatch):
    monkeypatch.setattr(factory.sys, 'platform', 'linux')
    class Broken:
        def __init__(self, *args, **kwargs):
            raise OSError('device unavailable')
    class Pynput:
        def __init__(self, key):
            self.key = key
        def is_key_available(self):
            return True
    module_with(monkeypatch, 'dictare.hotkey.evdev_listener', 'EvdevHotkeyListener', Broken)
    module_with(monkeypatch, 'dictare.hotkey.pynput_listener', 'PynputHotkeyListener', Pynput)
    result = factory.create_hotkey_listener(SimpleNamespace(key='f8', device='', mode_switch_modifier=None))
    assert result.key == 'f8'


def test_unsupported_key_reports_failure(monkeypatch):
    monkeypatch.setattr(factory.sys, 'platform', 'darwin')
    class Pynput:
        def __init__(self, key):
            pass
        def is_key_available(self):
            return False
    module_with(monkeypatch, 'dictare.hotkey.pynput_listener', 'PynputHotkeyListener', Pynput)
    with pytest.raises(RuntimeError, match='key f8 not supported'):
        factory.create_hotkey_listener(SimpleNamespace(key='f8'))
