"""Linux hotkey behavior using synthetic evdev devices and key events."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.hotkey.evdev_listener import EvdevHotkeyListener


@pytest.fixture
def evdev(monkeypatch):
    module = SimpleNamespace(ecodes=SimpleNamespace(EV_KEY=1, KEY_SCROLLLOCK=70, KEY_RIGHTALT=100, KEY={70: "KEY_SCROLLLOCK", 100: "KEY_RIGHTALT", 88: "KEY_F12"}))
    module.list_devices = Mock(return_value=[])
    module.InputDevice = Mock()
    monkeypatch.setitem(sys.modules, "evdev", module)
    return module


def device(path, name, keys):
    result = Mock()
    result.path, result.name = path, name
    result.capabilities.return_value = {1: keys}
    return result


def test_device_selection_prefers_keyboard_and_closes_others(evdev):
    remote = device("r", "Remote", [70])
    generic = device("g", "Input", [70])
    keyboard = device("k", "USB Keyboard", [70])
    evdev.list_devices.return_value = ["r", "g", "k"]
    evdev.InputDevice.side_effect = [remote, generic, keyboard]
    listener = EvdevHotkeyListener()
    assert listener._find_keyboard_device() is keyboard
    remote.close.assert_called_once()
    generic.close.assert_called_once()
    keyboard.close.assert_not_called()
    assert listener.get_selected_device_info() == ("k", "USB Keyboard")
    assert listener.get_key_name() == "Scrolllock"


def test_selection_respects_explicit_target_and_missing_keys(evdev):
    remote = device("r", "Remote", [70])
    evdev.list_devices.return_value = ["r"]
    evdev.InputDevice.return_value = remote
    assert EvdevHotkeyListener(target_device="remote")._find_keyboard_device() is remote
    with pytest.raises(RuntimeError, match="No keyboard"):
        EvdevHotkeyListener()._find_keyboard_device()
    with pytest.raises(ValueError, match="Unknown key"):
        EvdevHotkeyListener("KEY_MISSING")._find_keyboard_device()


def test_list_and_availability(evdev):
    keyboard = device("k", "Keyboard", [70, 88])
    evdev.list_devices.return_value = ["k"]
    evdev.InputDevice.return_value = keyboard
    listener = EvdevHotkeyListener()
    assert listener.is_key_available()
    assert listener.list_available_keys() == ["KEY_F12", "KEY_SCROLLLOCK"]
    assert listener.suggest_fallback_key() == "KEY_SCROLLLOCK"
    assert not EvdevHotkeyListener("NO_KEY").is_key_available()


def test_event_loop_dispatch_and_stop(evdev, monkeypatch):
    keyboard = device("k", "Keyboard", [70, 100])
    events = [(100, 1), (70, 1), (70, 0), (100, 0), (70, 1), (70, 2), (88, 1)]
    keyboard.read_loop.return_value = [SimpleNamespace(type=1, code=code, value=value) for code, value in events]
    listener = EvdevHotkeyListener(mode_switch_modifier="KEY_RIGHTALT")
    monkeypatch.setattr(listener, "_find_keyboard_device", lambda: keyboard)
    class Thread:
        def __init__(self, target, daemon):
            self.target = target
        def start(self):
            self.target()
        def is_alive(self):
            return False
    monkeypatch.setattr("dictare.hotkey.evdev_listener.threading.Thread", Thread)
    press, release, other, combo = Mock(), Mock(), Mock(), Mock()
    listener.start(press, release, other, combo)
    press.assert_called_once()
    release.assert_called_once()
    combo.assert_called_once()
    other.assert_called_once()
    assert listener.capture_next_key(0) is None
    listener.stop()
    keyboard.close.assert_called_once()
