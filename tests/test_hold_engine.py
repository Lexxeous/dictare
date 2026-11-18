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


def test_standard_mute_listens_only_for_resume_and_returns_to_hold_idle(monkeypatch):
    from dictare.core.openvip_messages import create_message

    monkeypatch.setattr('dictare.audio.beep.cancel_pending_feedback', lambda: None)
    monkeypatch.setattr('dictare.audio.beep.suspend_feedback', lambda **_: None)
    monkeypatch.setattr('dictare.audio.beep.resume_feedback', lambda: None)
    monkeypatch.setattr('dictare.tts.base.suspend_native_audio', lambda: True)
    monkeypatch.setattr('dictare.tts.base.resume_native_audio', lambda: None)
    engine = make_engine()
    engine.tts_mgr = MagicMock(available=False)
    engine._agent_mgr._current_agent_id = '__keyboard__'
    engine.mute()
    process_next(engine)
    assert engine._voice_muted and engine.state == AppState.LISTENING
    assert engine._should_process_capture()
    assert engine._pipeline.process(create_message('private conversation')) == []
    engine.inject_text('ok listen', capture_generation=engine._capture_generation)
    assert not engine._voice_muted
    assert not engine._should_process_capture()
    process_next(engine)
    assert engine.state == AppState.OFF
    engine.audio_manager.clear_queue.assert_called()
    engine.hotkey_down()
    assert engine._hold_capture_active
    engine.hotkey_other_key()
    process_next(engine)
    process_next(engine)


def test_muting_during_hold_discards_turn_and_keeps_voice_resume_enabled(monkeypatch):
    monkeypatch.setattr('dictare.audio.beep.cancel_pending_feedback', lambda: None)
    monkeypatch.setattr('dictare.audio.beep.suspend_feedback', lambda **_: None)
    monkeypatch.setattr('dictare.tts.base.suspend_native_audio', lambda: True)
    engine = make_engine()
    engine.tts_mgr = MagicMock(available=False)
    engine._agent_mgr._current_agent_id = '__keyboard__'
    engine.hotkey_down()
    process_next(engine)
    engine.mute()
    assert not engine._hold_capture_active
    process_next(engine)  # cancelled hold
    process_next(engine)  # resume-only listening
    process_next(engine)  # redundant resume-only request
    assert engine._voice_muted and engine.state == AppState.LISTENING
    assert engine._should_process_capture()
    engine.audio_manager.flush_vad.assert_not_called()


def test_restored_standard_mute_starts_in_resume_only_listening(monkeypatch):
    monkeypatch.setattr('dictare.audio.beep.suspend_feedback', lambda **_: None)
    monkeypatch.setattr('dictare.tts.base.suspend_native_audio', lambda: True)
    engine = make_engine()
    engine._controller.start = MagicMock()
    engine._voice_muted = True
    engine._agent_mgr._current_agent_id = '__keyboard__'
    engine.start_runtime(start_listening=False)
    assert engine.state == AppState.LISTENING
    assert engine._voice_muted and engine._should_process_capture()
    assert not engine._hold_capture_active


def test_factory_enables_experimental_hold_only_in_explicit_source_mode(monkeypatch):
    from unittest.mock import patch

    from dictare.core.engine import create_engine

    monkeypatch.setenv('DICTARE_DEV_EXPERIMENTAL_HOLD', '1')
    monkeypatch.delenv('DICTARE_DEV_MODE', raising=False)
    with patch('dictare.core.engine.DictareEngine') as constructor:
        create_engine(Config(), MagicMock())
        assert constructor.call_args.kwargs['experimental_hold'] is False
        monkeypatch.setenv('DICTARE_DEV_MODE', '1')
        create_engine(Config(), MagicMock())
        assert constructor.call_args.kwargs['experimental_hold'] is True


def test_factory_enables_hold_from_saved_configuration(monkeypatch):
    from unittest.mock import patch

    from dictare.core.engine import create_engine

    monkeypatch.delenv('DICTARE_DEV_MODE', raising=False)
    monkeypatch.delenv('DICTARE_DEV_EXPERIMENTAL_HOLD', raising=False)
    config = Config()
    config.hotkey.activation_mode = 'hold'
    with patch('dictare.core.engine.DictareEngine') as constructor:
        create_engine(config, MagicMock())
        assert constructor.call_args.kwargs['experimental_hold'] is True
