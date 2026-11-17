"""Strict mute closes capture while standard mute keeps voice resume."""

from unittest.mock import MagicMock

import numpy as np

from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState, HotkeyPressed, SetListening, TranscriptionCompleted


def test_strict_gate_rejects_stale_audio_and_requires_hotkey(monkeypatch):
    monkeypatch.setattr("dictare.audio.beep.stop_loop", lambda: None)
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine.audio_manager = MagicMock()
    engine.tts_mgr = MagicMock()
    engine._state_manager.transition(AppState.LISTENING, force=True)
    previous = engine._capture_generation
    engine.strict_mute()
    engine._on_vad_speech_start()
    engine._on_vad_speech_end(np.zeros(100))
    assert not engine.capture_allowed(previous)
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert engine.state == AppState.OFF
    assert engine.handle_protocol_command({"command": "stt.start"})["status"] == "error"
    engine._controller._handle_event(SetListening(on=True, source="api"))
    assert engine.state == AppState.OFF
    engine._controller._handle_event(HotkeyPressed(source="hotkey"))
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert engine.state == AppState.LISTENING
    assert not engine.capture_allowed(previous)
    assert engine.capture_allowed()
    engine.inject_text = MagicMock()
    engine._controller._handle_event(TranscriptionCompleted(text="old", capture_generation=previous))
    engine.inject_text.assert_not_called()


def test_standard_mute_does_not_close_capture_or_remove_voice_resume():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine.tts_mgr = MagicMock(available=False)
    engine.mute()
    assert engine._voice_muted
    assert engine.capture_allowed()
    engine.unmute()
    assert not engine._voice_muted


def test_strict_mute_does_not_bypass_pending_review(monkeypatch):
    from dictare.core.prompt_review import UnavailableReviewAgent

    monkeypatch.setattr("dictare.audio.beep.stop_loop", lambda: None)
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine.tts_mgr = MagicMock()
    draft = engine._review_slot.hold(UnavailableReviewAgent("codex"), [{"text": "pending"}])
    assert draft is not None
    engine.strict_mute()
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    engine._controller._handle_event(HotkeyPressed(source="hotkey"))
    assert engine._strict_muted
    assert engine.discard_review(draft.id)
    engine._controller._handle_event(HotkeyPressed(source="hotkey"))
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert not engine._strict_muted and engine.state == AppState.LISTENING


def test_native_transcription_finishing_after_strict_mute_is_discarded(monkeypatch):
    monkeypatch.setattr("dictare.audio.beep.stop_loop", lambda: None)
    engine = DictareEngine(Config(), logger=MagicMock(), hotkey_enabled=False)
    engine.tts_mgr = MagicMock()
    engine._state_manager.transition(AppState.LISTENING, force=True)
    old_generation = engine._capture_generation
    engine._stt = MagicMock()

    def finish_late(*args, **kwargs):
        engine.strict_mute()
        engine.resume_strict_mute()
        return MagicMock(text="private", language="en")

    engine._stt.transcribe.side_effect = finish_late
    engine._transcribe_job(np.zeros(16000), None, engine._stt_generation, old_generation)
    assert engine._last_text == ""
    assert engine.stats.count == 0
    engine._logger.log_transcription.assert_not_called()
