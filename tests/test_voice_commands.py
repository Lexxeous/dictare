"""Personal phrases reuse pipeline matching without rewriting advanced patterns."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dictare.config import (
    Config,
    VoiceCommandsConfig,
    load_config,
    set_config_value,
    set_config_values,
)
from dictare.core.engine import DictareEngine
from dictare.core.http_server import OpenVIPServer
from dictare.core.openvip_messages import create_message
from tests.test_http_server_extra import MockController, MockEngine


def personal_config() -> Config:
    config = Config(voice_commands=VoiceCommandsConfig(enabled=True, mute="Dictare mute", listen="Dictare listen", send="Dictare send"))
    config.pipeline.agent_filter.enabled = False
    return config


def test_custom_send_consumes_command_in_any_detected_language():
    engine = DictareEngine(personal_config(), hotkey_enabled=False)
    result = engine._pipeline.process(create_message("Write a test. Dictare send", language="fr"))
    assert len(result) == 1
    assert "submit" in result[0]["x_input"]["ops"]
    assert "dictare" not in result[0]["text"].lower()
    assert "Write a test" in result[0]["text"]


def test_custom_mute_and_listen_are_consumed_as_control_actions():
    engine = DictareEngine(personal_config(), hotkey_enabled=False)
    muted = engine._pipeline.process(create_message("Dictare mute"))
    assert muted[0]["x_mute"]["action"] == "mute"
    assert muted[0]["text"] == ""
    engine._voice_muted = True
    resumed = engine._pipeline.process(create_message("Dictare listen"))
    assert resumed[0]["x_mute"]["action"] == "unmute"
    assert resumed[0]["text"] == ""


def test_advanced_patterns_survive_switching_personal_commands_off():
    config = personal_config()
    config.pipeline.submit_filter.triggers = {"es": [["vale", "enviar"]]}
    before = config.pipeline.model_dump()
    engine = DictareEngine(config, hotkey_enabled=False)
    result = engine._pipeline.process(create_message("vale enviar", language="es"))
    assert "x_input" not in result[0]
    assert config.pipeline.model_dump() == before
    config.voice_commands.enabled = False
    restored = DictareEngine(config, hotkey_enabled=False)
    result = restored._pipeline.process(create_message("vale enviar", language="es"))
    assert "submit" in result[0]["x_input"]["ops"]
    assert config.pipeline.model_dump() == before


def test_personal_mode_does_not_enable_a_disabled_master_pipeline():
    config = personal_config()
    config.pipeline.enabled = False
    assert DictareEngine(config, hotkey_enabled=False)._pipeline is None


def test_personal_phrases_appear_in_stt_hotwords():
    engine = DictareEngine(personal_config(), hotkey_enabled=False)
    words = engine._collect_pipeline_trigger_words()
    assert {"dictare", "mute", "listen", "send"} <= words


def test_phrase_case_punctuation_accents_and_duplicates_use_existing_normalizer():
    commands = VoiceCommandsConfig(mute="Díctare, MUTE!\ndictare mute", listen="Dictare listen", send="Dictare send")
    assert commands.patterns("mute") == {"*": [["dictare", "mute"]]}


@pytest.mark.parametrize("mute,send", [("Dictare send", "dictare send"), ("send", "Dictare send"), ("dictare please send", "dictare send")])
def test_overlapping_actions_are_rejected(mute, send):
    with pytest.raises(ValueError, match="overlap"):
        VoiceCommandsConfig(mute=mute, send=send)


@pytest.mark.parametrize("phrase", ["", "   ", "!!!", "你好", " ".join(["word"] * 11), "\n".join(f"phrase{i}" for i in range(33))])
def test_invalid_or_unbounded_phrases_are_rejected(phrase):
    with pytest.raises(ValueError):
        VoiceCommandsConfig(mute=phrase)


def test_atomic_swap_preserves_comments_and_language_patterns(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('# Keep private choices\n[pipeline.mute_filter.mute_triggers]\nes = [["vale", "silencio"]] # Custom language\n')
    monkeypatch.setenv("DICTARE_CONFIG_PATH", str(path))
    original_patterns = load_config(path).pipeline.model_dump()
    set_config_values({"voice_commands.enabled": "true", "voice_commands.mute": "Dictare mute", "voice_commands.listen": "Dictare listen", "voice_commands.send": "Dictare send"}, path)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="overlap"):
        set_config_value("voice_commands.mute", "Dictare send", path)
    assert path.read_bytes() == original
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    result = client.post("/api/settings", json={"values": {"voice_commands.mute": "Dictare send", "voice_commands.send": "Dictare mute"}})
    assert result.status_code == 200
    config = load_config(path)
    assert config.voice_commands.mute == "Dictare send"
    assert config.voice_commands.send == "Dictare mute"
    assert config.pipeline.model_dump() == original_patterns
    assert "# Keep private choices" in path.read_text()
    assert "# Custom language" in path.read_text()


def test_invalid_personal_command_returns_readable_error_without_config_dump(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('editor = "private-editor-value"\n')
    monkeypatch.setenv("DICTARE_CONFIG_PATH", str(path))
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    response = client.post("/api/settings", json={"values": {"voice_commands.mute": "ok send"}})
    assert response.status_code == 400
    assert "overlap" in response.json()["detail"]
    assert "private-editor-value" not in response.text
    assert "input_value" not in response.text
    assert path.read_text() == 'editor = "private-editor-value"\n'


@pytest.mark.parametrize("environment_phrase", [None, "Dictare mute"])
def test_schema_exposes_effective_phrases_even_when_generic_string_fields_are_blank(tmp_path, monkeypatch, environment_phrase):
    path = tmp_path / "config.toml"
    path.write_text("")
    monkeypatch.setenv("DICTARE_CONFIG_PATH", str(path))
    if environment_phrase:
        monkeypatch.setenv("DICTARE_VOICE_COMMANDS_MUTE", environment_phrase)
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    with patch("dictare.audio.capture.AudioCapture.list_devices", return_value=[]), patch("dictare.audio.capture.AudioCapture.get_default_device", return_value=None):
        response = client.get("/api/settings/schema")
    assert response.status_code == 200
    data = response.json()
    assert data["values"]["voice_commands"]["mute"] == ""
    assert data["voice_commands"]["mute"] == (environment_phrase or "ok mute\nok hold on")
