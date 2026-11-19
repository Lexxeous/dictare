"""CoreAudio monitor tests with simulated OS callbacks."""

import ctypes
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from dictare.audio.device_monitor import (
    REASON_DEFAULT_INPUT,
    REASON_DEFAULT_OUTPUT,
    REASON_DEVICES,
    REASON_SLEEP,
    REASON_WAKE,
    CoreAudioDeviceMonitor,
)


def test_coreaudio_listeners_deliver_events_and_are_removed(monkeypatch):
    audio = Mock()
    audio.AudioObjectAddPropertyListener.side_effect = [0, 1, 0]
    monkeypatch.setattr(ctypes.cdll, 'LoadLibrary', lambda path: audio)
    events = []
    monitor = CoreAudioDeviceMonitor(events.append)
    monkeypatch.setattr(monitor, '_install_sleep_wake_observers', Mock())
    monitor.start()
    monitor.start()
    assert monitor.running
    assert audio.AudioObjectAddPropertyListener.call_count == 3
    for callback in monitor._callback_refs:
        assert callback(1, 0, None, None) == 0
    assert events == [REASON_DEFAULT_INPUT, REASON_DEFAULT_OUTPUT, REASON_DEVICES]
    monitor.stop()
    monitor.stop()
    assert not monitor.running
    assert audio.AudioObjectRemovePropertyListener.call_count == 3
    assert monitor._callback_refs == []


def test_callback_exceptions_do_not_cross_native_boundary(monkeypatch):
    audio = Mock()
    audio.AudioObjectAddPropertyListener.return_value = 0
    monkeypatch.setattr(ctypes.cdll, 'LoadLibrary', lambda path: audio)
    callback = Mock(side_effect=RuntimeError('callback error'))
    monitor = CoreAudioDeviceMonitor(callback)
    monitor._install_listeners()
    assert monitor._callback_refs[0](1, 0, None, None) == 0
    audio.AudioObjectRemovePropertyListener.side_effect = RuntimeError('remove error')
    monitor._remove_listeners()
    assert not monitor._callback_refs


def test_sleep_wake_observers_publish_and_unsubscribe(monkeypatch):
    callbacks = {}
    center = Mock()
    def add(name, obj, queue, callback):
        callbacks[name] = callback
        return name + '-token'
    center.addObserverForName_object_queue_usingBlock_.side_effect = add
    workspace = SimpleNamespace(sharedWorkspace=lambda: SimpleNamespace(notificationCenter=lambda: center))
    monkeypatch.setitem(sys.modules, 'AppKit', SimpleNamespace(NSWorkspace=workspace))
    events = []
    monitor = CoreAudioDeviceMonitor(events.append)
    monitor._install_sleep_wake_observers()
    callbacks['NSWorkspaceWillSleepNotification'](None)
    callbacks['NSWorkspaceDidWakeNotification'](None)
    assert events == [REASON_SLEEP, REASON_WAKE]
    monitor._remove_sleep_wake_observers()
    assert center.removeObserver_.call_count == 2
    assert monitor._workspace_observers == []
