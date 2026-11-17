"""Input suspension stays closed across recovery until an explicit resume."""

from unittest.mock import MagicMock

import pytest

from dictare.config import AudioConfig
from dictare.core.audio_manager import AudioManager


def test_suspend_and_resume_run_on_owner_and_block_recovery(monkeypatch):
    manager = AudioManager(AudioConfig())
    capture = MagicMock()
    capture.is_recording.return_value = False
    capture.wait_for_audio.return_value = True
    manager._audio = capture
    monkeypatch.setattr("dictare.audio.beep.set_audio_control_executor", lambda executor: None)
    try:
        manager.start_streaming(lambda: True, lambda: True)
        assert capture.start_streaming.call_count == 1
        manager.suspend_input()
        capture.stop_streaming.assert_called_once()
        assert manager.reconnect_reason is None
        manager._restart_input_stream()
        assert capture.start_streaming.call_count == 1
        assert not manager.reconnect(lambda chunk: None)
        manager.resume_input()
        assert capture.start_streaming.call_count == 2
    finally:
        manager._control.shutdown()


def test_failed_resume_leaves_input_suspended(monkeypatch):
    manager = AudioManager(AudioConfig())
    capture = MagicMock()
    capture.is_recording.return_value = False
    capture.wait_for_audio.return_value = False
    manager._audio = capture
    monkeypatch.setattr("dictare.audio.beep.set_audio_control_executor", lambda executor: None)
    try:
        manager.start_streaming(lambda: True, lambda: True, suspended=True)
        capture.start_streaming.assert_not_called()
        with pytest.raises(RuntimeError, match="no audio callbacks"):
            manager.resume_input()
        assert manager._input_suspended
        assert manager.reconnect_reason is None
    finally:
        manager._control.shutdown()
