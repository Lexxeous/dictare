"""Voice mute suppresses new feedback without claiming capture is stopped."""

from unittest.mock import MagicMock

from dictare.app.controller import _ControllerEvents
from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState


def test_muted_state_changes_suppress_feedback_but_stop_existing_loop(monkeypatch):
    play = MagicMock()
    stop = MagicMock()
    monkeypatch.setattr("dictare.audio.beep.play_audio", play)
    monkeypatch.setattr("dictare.audio.beep.play_sound_file_async", play)
    monkeypatch.setattr("dictare.audio.beep.start_loop", play)
    monkeypatch.setattr("dictare.audio.beep.stop_loop", stop)
    config = Config()
    engine = DictareEngine(config, hotkey_enabled=False)
    engine._voice_muted = True
    events = _ControllerEvents(config)
    events.set_engine(engine)
    events.on_state_change(AppState.TRANSCRIBING, AppState.LISTENING, "transcription_complete")
    events.on_state_change(AppState.RECORDING, AppState.TRANSCRIBING, "speech_end:9000")
    engine._play_focus_gated_sound("transcribed")
    stop.assert_called_once()
    play.assert_not_called()


def test_agent_announcement_is_silent_only_while_muted():
    config = Config()
    engine = DictareEngine(config, hotkey_enabled=False)
    engine.speak_agent = MagicMock()
    events = _ControllerEvents(config)
    events.set_engine(engine)
    engine._voice_muted = True
    events.on_agent_change("codex", 0)
    engine.speak_agent.assert_not_called()
    engine._voice_muted = False
    events.on_agent_change("codex", 0)
    engine.speak_agent.assert_called_once_with("codex")


def test_standard_mute_status_stays_muted_during_background_speech(monkeypatch):
    import dictare.core.status_report as status_report

    monkeypatch.setattr(status_report, "audio_devices", lambda: {})
    monkeypatch.setattr(status_report, "permissions", lambda: {})
    monkeypatch.setattr(status_report, "hotkey_active", lambda engine: False)
    monkeypatch.setattr(status_report, "hotkey_status_raw", lambda engine: "unknown")
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine._voice_muted = True
    for state in (AppState.LISTENING, AppState.RECORDING, AppState.TRANSCRIBING):
        engine._state_manager.transition(state, force=True)
        status = engine.get_status()
        assert status["platform"]["state"] == "muted"
        assert status["stt"]["active"] is True  # Voice resume still needs recognition.
    engine._state_manager.transition(AppState.OFF, force=True)
    assert engine.get_status()["platform"]["state"] == "off"
