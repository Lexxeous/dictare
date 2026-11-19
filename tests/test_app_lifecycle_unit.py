"""Unit tests for application startup and lifecycle coordination."""

import errno
from unittest.mock import MagicMock

import pytest

from dictare.app.controller import AppController, _ControllerEvents
from dictare.core.fsm import AppState


@pytest.fixture
def startup(monkeypatch):
    config = MagicMock()
    config.log_level = "debug"
    config.output.mode = "agents"
    config.server.host = "localhost"
    config.server.port = 12345
    engine = MagicMock()
    engine.restore_state.return_value = False
    server = MagicMock()
    server.wait_started.return_value = True
    binding = MagicMock()
    log = MagicMock()
    monkeypatch.setattr("dictare.core.engine.create_engine", MagicMock(return_value=engine))
    monkeypatch.setattr("dictare.core.http_server.OpenVIPServer", MagicMock(return_value=server))
    monkeypatch.setattr("dictare.app.bindings.KeyboardBindingManager", MagicMock(return_value=binding))
    monkeypatch.setattr("dictare.logging.jsonl.JSONLLogger", MagicMock(return_value=log))
    controller = AppController(config)
    monkeypatch.setattr(controller, "_check_single_instance", MagicMock())
    monkeypatch.setattr(controller, "_cleanup_pid", MagicMock())
    monkeypatch.setattr(controller, "_display_session_stats", MagicMock())
    return controller, engine, server, binding, log


def test_start_restores_state_and_stops_in_order(startup):
    controller, engine, server, binding, log = startup
    engine.requested_exit_code = 3
    controller.start()
    engine.restore_state.assert_called_once_with(True)
    server.wait_started.assert_called_once_with(timeout=5.0)
    engine.init_components.assert_called_once_with(headless=True, http_server=server)
    engine.start_runtime.assert_called_once_with(start_listening=False)
    binding.start.assert_called_once()
    controller.stop()
    engine.save_state.assert_called_once()
    assert engine.running is False
    binding.stop.assert_called_once()
    server.stop.assert_called_once()
    engine.stop.assert_called_once()
    log.close.assert_called_once()
    assert controller.exit_code == 3
    assert controller.wait_for_shutdown(0)


@pytest.mark.parametrize("error, message", [
    (OSError(errno.EADDRINUSE, "occupied"), "already in use"),
    (RuntimeError("broken"), "failed to start: broken"),
])
def test_start_rejects_failed_server(startup, error, message):
    controller, engine, server, binding, _ = startup
    server.wait_started.return_value = False
    server._start_error = error
    with pytest.raises(RuntimeError, match=message):
        controller.start()
    controller._cleanup_pid.assert_called_once()
    engine.init_components.assert_not_called()
    binding.start.assert_not_called()


def test_start_without_bindings_in_development(startup, monkeypatch):
    controller, engine, _, binding, _ = startup
    monkeypatch.setenv("DICTARE_DEV_MODE", "1")
    controller.start(with_bindings=False, start_listening=False)
    from dictare.core.engine import create_engine
    assert create_engine.call_args.kwargs["hotkey_enabled"] is False
    engine.restore_state.assert_called_once_with(False)
    binding.start.assert_not_called()


def test_audio_feedback_and_muting(monkeypatch):
    from dictare.audio import beep
    config = MagicMock()
    config.audio.headphones_mode = False
    config.audio.sounds = {}
    config.audio.advanced.transcribing_sound_min_ms = 8000
    engine = MagicMock()
    engine._voice_muted = False
    engine._strict_muted = False
    events = _ControllerEvents(config)
    events.set_engine(engine)
    for name in ("play_audio", "start_loop", "stop_loop", "play_sound_file_async"):
        monkeypatch.setattr(beep, name, MagicMock())
    monkeypatch.setattr(beep, "get_sound_for_event", MagicMock(return_value=(True, "sound.wav")))
    monkeypatch.setattr(beep, "is_looping", MagicMock(return_value=True))
    events.on_state_change(AppState.OFF, AppState.LISTENING, "start")
    beep.play_audio.assert_called_once_with("sound.wav", pause_mic=True, controller=engine._controller, volume=1.0)
    events.on_state_change(AppState.LISTENING, AppState.TRANSCRIBING, "speech_end:9000")
    beep.start_loop.assert_called_once_with("sound.wav", volume=1.0)
    events.on_state_change(AppState.TRANSCRIBING, AppState.LISTENING, "done")
    beep.stop_loop.assert_called_once()
    beep.play_sound_file_async.assert_called_once_with("sound.wav", volume=1.0)
    engine._play_focus_gated_sound.assert_called_once_with("transcribed")
    engine._voice_muted = True
    events.on_state_change(AppState.LISTENING, AppState.OFF, "stop")
    assert beep.play_audio.call_count == 1
