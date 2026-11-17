"""Experimental hold capture remains gated until an actual press and release."""

from unittest.mock import MagicMock

import numpy as np

from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState, TranscriptionCompleted


def make_engine():
    engine = DictareEngine(Config(), hotkey_enabled=False, experimental_hold=True)
    engine.audio_manager = MagicMock()
    engine.audio_manager.sample_rate = 16000
    engine.running = True
    return engine


def process_next(engine):
    engine._controller._handle_event(engine._controller._queue.get_nowait())


def test_hold_press_release_delivers_one_turn_and_reopens_only_after_completion():
    engine = make_engine()
    engine.transcribe_and_process = MagicMock()
    engine.inject_text = MagicMock()
    engine.hotkey_tap()  # Legacy tap transport is not a hold.
    assert engine._controller._queue.empty()
    engine.hotkey_down()
    process_next(engine)
    assert engine.state == AppState.LISTENING and engine._hold_capture_active
    engine.audio_manager.set_vad_explicit_turn.assert_called_once_with(True)
    def flush():
        engine._on_vad_speech_end(np.zeros(5000, dtype=np.float32))
        return True
    engine.audio_manager.flush_vad.side_effect = flush
    engine.hotkey_up()
    assert not engine._hold_capture_active
    process_next(engine)
    process_next(engine)
    assert engine.state == AppState.TRANSCRIBING
    engine.hotkey_down()  # Still draining, so no new turn.
    assert engine._controller._queue.empty()
    engine._controller._handle_event(TranscriptionCompleted(text='hello', source='test', capture_generation=engine._capture_generation))
    assert engine.state == AppState.OFF
    engine.inject_text.assert_called_once()
    assert engine.audio_manager.set_vad_explicit_turn.call_args_list[-1].args == (False,)
    engine.hotkey_down()
    assert engine._hold_capture_active
    engine.hotkey_other_key()
    process_next(engine)  # Start
    process_next(engine)  # Cancel
    engine._controller._cancel_transcription_watchdog()


def test_timeout_and_maximum_duration_cancel_without_flushing():
    for limit in ('timeout', 'maximum'):
        engine = make_engine()
        engine.hotkey_down()
        process_next(engine)
        if limit == 'timeout':
            engine._hold_gate._expire(1)
        else:
            engine._on_max_speech_duration()
        assert not engine._hold_capture_active
        process_next(engine)
        assert engine.state == AppState.OFF
        engine.audio_manager.flush_vad.assert_not_called()
        engine.audio_manager.reset_vad.assert_called_once()
        assert engine.audio_manager.set_vad_explicit_turn.call_args_list[-1].args == (False,)


def test_hold_does_not_start_while_reviewing():
    engine = make_engine()
    engine.review_pending = lambda: True
    engine.hotkey_down()
    assert engine._controller._queue.empty()


def test_strict_mute_hotkey_recovers_to_idle_without_capturing(monkeypatch):
    monkeypatch.setattr("dictare.audio.beep.resume_feedback", lambda: None)
    monkeypatch.setattr("dictare.tts.base.resume_native_audio", lambda: None)
    engine = make_engine()
    engine.tts_mgr = MagicMock()
    engine._strict_muted = True
    engine.hotkey_down()
    process_next(engine)
    assert not engine._strict_muted
    assert engine.state == AppState.OFF
    assert not engine._hold_capture_active
    assert engine._controller._queue.empty()
    engine.hotkey_up()  # The recovery press is not a captured turn.
    engine.hotkey_down()
    assert engine._hold_capture_active
    engine.hotkey_other_key()
    process_next(engine)
    process_next(engine)


def test_strict_mute_can_recover_from_legacy_tap_without_starting_a_hold(monkeypatch):
    monkeypatch.setattr("dictare.audio.beep.resume_feedback", lambda: None)
    monkeypatch.setattr("dictare.tts.base.resume_native_audio", lambda: None)
    engine = make_engine()
    engine.tts_mgr = MagicMock()
    engine._strict_muted = True
    engine.hotkey_tap()
    process_next(engine)
    assert not engine._strict_muted and engine.state == AppState.OFF
    assert not engine._hold_capture_active


def test_hold_press_before_runtime_is_ignored():
    engine = DictareEngine(Config(), hotkey_enabled=False, experimental_hold=True)
    engine.hotkey_down()
    assert engine._controller._queue.empty()
    assert not engine._hold_capture_active


def test_failed_strict_recovery_does_not_start_a_hold():
    engine = make_engine()
    engine._strict_muted = True
    engine.audio_manager.resume_input.side_effect = RuntimeError("unavailable")
    engine.hotkey_down()
    process_next(engine)
    assert engine._strict_muted and engine.state == AppState.OFF
    assert not engine._hold_capture_active
    assert engine._controller._queue.empty()
