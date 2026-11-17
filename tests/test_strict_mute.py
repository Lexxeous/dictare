"""Strict mute closes capture while standard mute keeps voice resume."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState, HotkeyPressed, SetListening, TranscriptionCompleted


@pytest.fixture(autouse=True)
def isolate_output_gates(monkeypatch):
    monkeypatch.setattr("dictare.audio.beep.suspend_feedback", MagicMock())
    monkeypatch.setattr("dictare.audio.beep.resume_feedback", MagicMock())
    monkeypatch.setattr("dictare.tts.base.suspend_native_audio", MagicMock())
    monkeypatch.setattr("dictare.tts.base.resume_native_audio", MagicMock())


def test_strict_gate_rejects_stale_audio_and_requires_hotkey(monkeypatch):
    monkeypatch.setattr("dictare.audio.beep.stop_loop", lambda: None)
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine.audio_manager = MagicMock()
    engine.tts_mgr = MagicMock()
    engine._state_manager.transition(AppState.LISTENING, force=True)
    previous = engine._capture_generation
    engine.strict_mute()
    engine.audio_manager.suspend_input.assert_called_once()
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
    engine.audio_manager.resume_input.assert_called_once()
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


def test_failed_input_reopen_keeps_strict_gate_closed(monkeypatch):
    monkeypatch.setattr("dictare.audio.beep.stop_loop", lambda: None)
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine.audio_manager = MagicMock()
    engine.audio_manager.resume_input.side_effect = RuntimeError("input unavailable")
    engine.tts_mgr = MagicMock()
    engine.strict_mute()
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    engine._controller._handle_event(HotkeyPressed(source="hotkey"))
    assert engine._strict_muted
    assert not engine.capture_allowed()
    assert engine.state == AppState.OFF
    assert engine._controller._queue.empty()


def test_strict_mute_rejects_new_tts_requests():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine.tts_mgr = MagicMock()
    engine._strict_muted = True
    engine.speak_text("private")
    engine.speak_agent("codex")
    assert engine.handle_speech({"text": "private"})["status"] == "error"
    engine.tts_mgr.speak_text.assert_not_called()
    engine.tts_mgr.speak_agent.assert_not_called()
    engine.tts_mgr.handle_speech.assert_not_called()


def test_unconfirmed_worker_interrupt_is_not_silently_marked_safe():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine.tts_mgr = MagicMock()
    engine.tts_mgr.suspend_for_strict.return_value = False
    engine.strict_mute()
    assert engine._strict_muted
    assert "did not confirm" in engine._strict_audio_error


def test_status_reports_strict_gate_and_failure_separately(monkeypatch):
    import dictare.core.status_report as status_report
    from dictare.status import resolve_display_state

    monkeypatch.setattr(status_report, "audio_devices", lambda: {})
    monkeypatch.setattr(status_report, "permissions", lambda: {})
    monkeypatch.setattr(status_report, "hotkey_active", lambda engine: False)
    monkeypatch.setattr(status_report, "hotkey_status_raw", lambda engine: "unknown")
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine._strict_muted = True
    engine._strict_transitioning = True
    engine._strict_audio_error = "Could not close the microphone input."
    status = engine.get_status()
    assert status["stt"]["active"] is False
    assert status["platform"]["state"] == "strict_muted"
    assert status["platform"]["strict_mute_pending"] is True
    assert status["platform"]["strict_mute_error"] == "Could not close the microphone input."
    assert resolve_display_state(status["platform"]) == ("strict_muted", "dim")
