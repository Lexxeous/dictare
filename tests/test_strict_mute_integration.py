"""Exercise strict mute and the source hotkey through the actual HTTP routes."""

import threading
import time
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState, HotkeyPressed
from dictare.core.http_server import OpenVIPServer


def wait_until(predicate):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        threading.Event().wait(0.01)
    assert predicate()


def test_source_strict_mute_stops_capture_and_resumes_only_by_hotkey(monkeypatch):
    import dictare.core.status_report as status_report

    monkeypatch.setenv("DICTARE_DEV_MODE", "1")
    monkeypatch.setattr("dictare.audio.beep.suspend_feedback", lambda **kwargs: None)
    monkeypatch.setattr("dictare.audio.beep.resume_feedback", lambda: None)
    monkeypatch.setattr("dictare.tts.base.suspend_native_audio", lambda: True)
    monkeypatch.setattr("dictare.tts.base.resume_native_audio", lambda: None)
    monkeypatch.setattr(status_report, "audio_devices", lambda: {})
    monkeypatch.setattr(status_report, "permissions", lambda: {})
    monkeypatch.setattr(status_report, "hotkey_active", lambda engine: False)
    monkeypatch.setattr(status_report, "hotkey_status_raw", lambda engine: "unknown")
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine.audio_manager = MagicMock()
    engine.audio_manager.get_actual_devices.return_value = {"input": None, "output": None}
    engine.tts_mgr = MagicMock()
    engine.tts_mgr.suspend_for_mute.return_value = True
    controller = MagicMock()
    controller.on_hotkey_tap.side_effect = lambda: engine._controller.send(HotkeyPressed(source="test"))
    server = OpenVIPServer(engine, controller)
    client = TestClient(server._app, base_url="http://127.0.0.1:18770", client=("127.0.0.1", 1234))
    engine._state_manager.transition(AppState.LISTENING, force=True)
    engine._controller.start()
    try:
        result = client.post("/openvip/control", json={"command": "stt.strict_mute"})
        assert result.json()["status"] == "ok"
        wait_until(lambda: engine.state == AppState.OFF)
        status = client.get("/openvip/status").json()
        assert status["platform"]["state"] == "strict_muted"
        assert status["stt"]["active"] is False
        engine.audio_manager.suspend_input.assert_called_once()
        assert client.post("/openvip/control", json={"command": "stt.start"}).json()["status"] == "error"
        assert client.post("/api/dev/hotkey").json()["status"] == "ok"
        wait_until(lambda: engine.state == AppState.LISTENING and not engine._strict_muted)
        engine.audio_manager.resume_input.assert_called_once()
    finally:
        engine._controller.stop()
