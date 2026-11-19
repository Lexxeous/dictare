"""Audio recovery behavior without opening real sound devices."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.core import audio_manager as module


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(module, "AudioControl", Mock())
    config = SimpleNamespace(input_device="headset", advanced=SimpleNamespace(device=None, sample_rate=16000, channels=1))
    return module.AudioManager(config)


def test_restart_stream_verifies_audio_before_resetting_vad(manager, monkeypatch):
    capture = Mock()
    capture.wait_for_audio.return_value = True
    factory = Mock(return_value=capture)
    monkeypatch.setattr(module, "AudioCapture", factory)
    manager.reset_vad = Mock()
    manager._restart_input_stream()
    factory.assert_called_once_with(sample_rate=16000, channels=1, device="headset")
    capture.start_streaming.assert_called_once_with(manager.on_audio_chunk)
    manager.reset_vad.assert_called_once()
    assert manager._audio is capture


def test_restart_stream_discards_zombie(manager, monkeypatch):
    capture = Mock()
    capture.wait_for_audio.return_value = False
    monkeypatch.setattr(module, "AudioCapture", Mock(return_value=capture))
    manager.reset_vad = Mock()
    manager._restart_input_stream()
    capture.stop_streaming.assert_called_once()
    manager.reset_vad.assert_not_called()
    assert manager._audio is None


def test_reconnect_retries_zombie_and_resets_vad(manager, monkeypatch):
    first, second = Mock(), Mock()
    first.wait_for_audio.return_value = False
    second.wait_for_audio.return_value = True
    factory = Mock(side_effect=[first, second])
    factory.get_default_device.return_value = {"name": "headset"}
    monkeypatch.setattr(module, "AudioCapture", factory)
    monkeypatch.setattr(module.time, "sleep", Mock())
    manager._reinit_portaudio = Mock()
    manager._stop_audio_output_owned = Mock()
    manager.reset_vad = Mock()
    manager._device_monitor = Mock()
    manager._on_reconnect_attempt = Mock()
    manager._on_reconnect_success = Mock()
    callback = Mock()
    assert manager._reconnect_owned(callback)
    first.stop_streaming.assert_called_once()
    second.start_streaming.assert_called_once_with(callback)
    manager._reinit_portaudio.assert_called_once()
    manager.reset_vad.assert_called_once()
    manager._device_monitor.stop.assert_called_once()
    manager._device_monitor.start.assert_called_once()
    assert manager._on_reconnect_attempt.call_count == 2
    manager._on_reconnect_success.assert_called_once_with("headset")


def test_reconnect_circuit_breaker_prevents_device_access(manager, monkeypatch):
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)
    factory = Mock()
    monkeypatch.setattr(module, "AudioCapture", factory)
    manager._reconnect_timestamps = [99.0] * manager._MAX_RECONNECTS
    assert not manager._reconnect_owned(Mock())
    factory.assert_not_called()
