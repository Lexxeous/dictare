"""Exercise hotkey event handling without a real keyboard listener."""

import sys
from enum import Enum
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.hotkey.pynput_listener import PynputHotkeyListener


class Key(Enum):
    scroll_lock = 1
    f12 = 2
    enter = 3


@pytest.fixture
def keyboard(monkeypatch):
    listener = Mock()
    module = SimpleNamespace(Key=Key, Listener=Mock(return_value=listener))
    monkeypatch.setitem(sys.modules, "pynput", SimpleNamespace(keyboard=module))
    return module, listener


def test_start_dispatch_and_stop(keyboard):
    module, listener = keyboard
    hotkey = PynputHotkeyListener()
    press, release, other = Mock(), Mock(), Mock()
    hotkey.start(press, release, other)
    listener.start.assert_called_once()
    hotkey._handle_press(Key.scroll_lock)
    hotkey._handle_press(Key.f12)
    hotkey._handle_release(Key.scroll_lock)
    press.assert_called_once()
    release.assert_called_once()
    other.assert_called_once()
    hotkey.stop()
    listener.stop.assert_called_once()
    listener.join.assert_called_once_with(timeout=2.0)
    assert hotkey._on_press is None


def test_key_conversion_and_unknown(keyboard):
    hotkey = PynputHotkeyListener("KEY_ENTER")
    assert hotkey.is_key_available()
    assert hotkey._pynput_to_evdev(Key.f12) == "KEY_F12"
    assert hotkey._pynput_to_evdev(Key.enter) == "KEY_ENTER"
    assert hotkey._pynput_to_evdev("a") is None
    assert hotkey.get_key_name() == "Enter"
    hotkey.key_name = "KEY_NONEXISTENT"
    with pytest.raises(ValueError, match="Unknown key"):
        hotkey.start(Mock(), Mock())


def test_capture_swallows_normal_events(keyboard, monkeypatch):
    import dictare.hotkey.pynput_listener as module
    hotkey = PynputHotkeyListener()
    assert hotkey.capture_next_key() is None
    hotkey._listener = object()
    event = Mock()
    event.wait.side_effect = lambda **kwargs: hotkey._handle_press(Key.f12)
    monkeypatch.setattr(module, "threading", SimpleNamespace(Event=lambda: event))
    assert hotkey.capture_next_key(timeout=0.1) == "KEY_F12"
    event.set.assert_called_once()
    assert hotkey._capture_event is None
