"""Behavioral tests for the status panel's formatting and polling."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rich.console import Console

from dictare.cli.panel import StatusPanel


@pytest.fixture
def panel(monkeypatch):
    monkeypatch.setattr("dictare.cli.panel.Client", Mock())
    return StatusPanel(Console(), "http://localhost:1234/", poll_interval=0)


def test_fetch_status_and_connection_failure(panel):
    panel._client.get_status.return_value = SimpleNamespace(platform={"state": "listening"})
    assert panel._fetch_status() == {"platform": {"state": "listening"}}
    panel._client.get_status.side_effect = ConnectionRefusedError()
    assert panel._fetch_status() is None


@pytest.mark.parametrize("key,expected", [("KEY_LEFTMETA", "Super/Meta"), ("KEY_SCROLLLOCK", "Scroll Lock"), ("KEY_A", "A")])
def test_hotkey_formatting(panel, monkeypatch, key, expected):
    monkeypatch.setattr("dictare.cli.panel.sys.platform", "linux")
    assert expected in panel._format_hotkey({"key": key, "bound": False})
    assert "not bound" in panel._format_hotkey({"key": key})
    assert "double-tap" in panel._format_hotkey({"key": key, "bound": True})


def test_output_stats_and_last_text(panel):
    agents = panel._format_output({"mode": "agents", "available_agents": ["one", "two"], "current_agent": "two"})
    assert "[bold green]two" in agents and "[dim]one" in agents
    assert "waiting for agents" in panel._format_output({"mode": "agents"})
    assert "keyboard" in panel._format_output({})
    assert "--" in panel._format_stats({})
    assert "1.5m" in panel._format_stats({"transcriptions": 1, "words": 5, "audio_seconds": 90})
    panel._status = {"platform": {"stt": {"last_text": "x" * 60}}}
    assert panel._format_last_text() == '"' + "x" * 55 + '..."'


@pytest.mark.parametrize("state,expected", [("done", "✓"), ("error", "error"), ("loading", "ETA 5s"), ("pending", "waiting")])
def test_model_line_states(panel, state, expected):
    result = panel._build_model_line("STT", "model", "CPU", state, 5, 10, suffix="warning")
    assert expected in result
    assert "warning" in result


def test_panel_loading_and_error_display(panel, monkeypatch):
    monkeypatch.setattr("dictare.utils.hardware.detect_nvidia_gpu", lambda: True)
    panel._status = {"platform": {"version": "test", "state": "listening", "stt": {"device": "cpu"}, "tts": {"engine": "say", "available": False}, "loading": {"active": True, "models": [{"name": "tts", "status": "loading"}]}}}
    loading = panel._build_panel()
    assert "Loading" in loading.title
    assert "GPU detected" in loading.renderable
    assert "dictare dependencies resolve" in loading.renderable
    panel._status["platform"]["loading"]["active"] = False
    ready = panel._build_panel()
    assert ready.border_style == "green"
    assert "LISTENING" in ready.renderable


def test_poll_waits_for_connection_then_stops_after_disconnect(panel, monkeypatch):
    live = Mock()
    monkeypatch.setattr("dictare.cli.panel.Live", Mock(return_value=live))
    live.__enter__ = Mock(return_value=live)
    live.__exit__ = Mock(return_value=False)
    panel._fetch_status = Mock(side_effect=[None, {"platform": {"stt": {"device": "mlx"}}}, None])
    panel.run()
    assert panel._fetch_status.call_count == 3
    assert live.update.call_count == 2
    panel.stop()
    assert panel._stop_event.is_set()
