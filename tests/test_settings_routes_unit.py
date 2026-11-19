"""Settings API behavior using an in-process client and mocked side effects."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dictare.core.http_routes_settings import register_settings_routes


@pytest.fixture
def api(monkeypatch):
    server = SimpleNamespace(engine=Mock(), notify_status_change=Mock())
    app = FastAPI()
    register_settings_routes(app, server)
    set_value, delete_value, set_values = Mock(), Mock(), Mock()
    monkeypatch.setattr("dictare.config.set_config_value", set_value)
    monkeypatch.setattr("dictare.config.delete_config_value", delete_value)
    monkeypatch.setattr("dictare.config.set_config_values", set_values)
    monkeypatch.setattr("dictare.config.load_config", lambda: "config")
    monkeypatch.setattr("dictare.config.get_config_value", lambda key, config: "resolved")
    return TestClient(app), server, set_value, delete_value, set_values


@pytest.mark.parametrize("body", [[], {}, {"key": "x"}, {"values": {}}, {"values": {"x": None}}, {"values": {}, "profiles": []}, {"values": {}, "delete_profiles": [2]}, {"values": {}, "create_profiles": [2]}])
def test_settings_reject_invalid_requests(api, body):
    client, _, _, _, set_values = api
    assert client.post("/api/settings", json=body).status_code == 400
    set_values.assert_not_called()


def test_batch_settings_normalize_values(api):
    client, _, _, _, set_values = api
    response = client.post("/api/settings", json={"values": {"a": "", "b": True, "c": ["x"]}, "create_profiles": ["new"]})
    assert response.json() == {"status": "ok"}
    set_values.assert_called_once_with({"a": None, "b": "True", "c": ["x"]}, profile_updates={}, create_profiles=["new"], delete_profiles=[])


def test_single_setting_updates_and_resets(api):
    client, _, set_value, delete_value, _ = api
    assert client.post("/api/settings", json={"key": "a", "value": 7}).json()["value"] == "resolved"
    set_value.assert_called_once_with("a", "7")
    assert client.post("/api/settings", json={"key": "a", "value": ""}).status_code == 200
    delete_value.assert_called_once_with("a")


@pytest.mark.parametrize("error,status", [(KeyError("unknown"), 404), (ValueError("invalid"), 400)])
def test_setting_errors_are_reported(api, error, status):
    client, _, set_value, _, set_values = api
    set_value.side_effect = error
    set_values.side_effect = error
    assert client.post("/api/settings", json={"key": "a", "value": "b"}).status_code == status
    assert client.post("/api/settings", json={"values": {"a": "b"}}).status_code == status


def test_audio_device_switches_and_default(api):
    client, server, set_value, delete_value, _ = api
    assert client.post("/api/audio/device", json={"type": "invalid"}).status_code == 400
    assert client.post("/api/audio/device", json={"type": "input", "device": "mic"}).status_code == 200
    set_value.assert_called_once_with("audio.input_device", "mic")
    server.engine.reset_audio_input.assert_called_once()
    assert client.post("/api/audio/device", json={"type": "output", "device": ""}).status_code == 200
    delete_value.assert_called_once_with("audio.output_device")
    server.engine.reset_audio_output.assert_called_once_with("")
    assert server.notify_status_change.call_count == 2


def test_audio_devices_and_presets(api, monkeypatch):
    from dictare.audio.capture import AudioCapture
    client, *_ = api
    monkeypatch.setattr(AudioCapture, "list_devices", lambda: [{"name": "Mic"}])
    monkeypatch.setattr(AudioCapture, "list_output_devices", lambda: [{"name": "Speaker"}])
    monkeypatch.setattr(AudioCapture, "get_default_device", lambda: {"name": "Mic"})
    monkeypatch.setattr(AudioCapture, "get_default_output_device", lambda: {"name": "Speaker"})
    monkeypatch.setattr("dictare.config.list_config_keys", lambda: [("audio.input_device", "str", "", "", ""), ("audio.output_device", "str", "", "", "")])
    assert client.get("/api/audio/devices").json()["default_input"] == {"name": "Mic"}
    presets = client.get("/api/settings/presets").json()
    assert presets["audio.input_device"]["default"] == "Mic"
    assert presets["audio.output_device"]["values"] == [{"value": "Speaker", "label": "Speaker"}]


def test_native_open_rejects_nonlocal_request(api):
    client, *_ = api
    assert client.post("/api/system/open-app").status_code == 403
