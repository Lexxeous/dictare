"""Test speech CLI dispatch and failure handling without an engine."""

import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import openvip
import pytest
import typer
from typer.testing import CliRunner

import dictare.config
from dictare.cli import speak


@pytest.fixture
def cli(monkeypatch):
    app = typer.Typer()
    speak.register(app)
    config = SimpleNamespace(server=SimpleNamespace(host="localhost", port=9000), tts=SimpleNamespace(engine="say", language="en", speed=200, voice=""))
    monkeypatch.setattr(dictare.config, "load_config", lambda *args: config)
    return app


def test_speak_forwards_explicit_overrides(cli, monkeypatch):
    client = Mock()
    client.speak.return_value = SimpleNamespace(duration_ms=42)
    factory = Mock(return_value=client)
    monkeypatch.setattr(openvip, "Client", factory)
    result = CliRunner().invoke(cli, ["hello", "-e", "kokoro", "-l", "fr", "-v", "voice", "-s", "180", "--verbose"])
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with("http://localhost:9000/openvip", timeout=300.0)
    client.speak.assert_called_once_with("hello", engine="kokoro", speed=180, language="fr", voice="voice")
    assert "42ms" in result.output


def test_stdin_invalid_engine_and_engine_listing(cli):
    result = CliRunner().invoke(cli, ["--list-engines"])
    assert result.exit_code == 0 and "espeak" in result.output
    result = CliRunner().invoke(cli, ["hello", "--engine", "unknown"])
    assert result.exit_code == 1 and "Unknown TTS engine" in result.output
    result = CliRunner().invoke(cli, [], input="  ")
    assert result.exit_code == 0 and "Usage:" in result.output


def test_stop_success_and_unreachable(cli, monkeypatch):
    client = Mock()
    monkeypatch.setattr(openvip, "Client", lambda *args, **kwargs: client)
    assert CliRunner().invoke(cli, ["stop"]).exit_code == 0
    client.stop_speech.assert_called_once()
    client.stop_speech.side_effect = URLError("refused")
    result = CliRunner().invoke(cli, ["stop"])
    assert result.exit_code == 1 and "Engine not running" in result.output


def test_http_error_and_timeout_stop(cli, monkeypatch):
    client = Mock()
    monkeypatch.setattr(openvip, "Client", lambda *args, **kwargs: client)
    body = io.BytesIO(json.dumps({"detail": "bad voice"}).encode())
    client.speak.side_effect = HTTPError("http://localhost", 422, "bad", {}, body)
    result = CliRunner().invoke(cli, ["hello"])
    assert result.exit_code == 1 and "bad voice" in result.output
    client.speak.side_effect = URLError(TimeoutError("timed out"))
    result = CliRunner().invoke(cli, ["hello"])
    assert result.exit_code == 1 and "audio stopped" in result.output
    client.stop_speech.assert_called_once()


def test_voice_listing_and_offline_message(cli, monkeypatch):
    import urllib.request
    # Context manager methods are looked up on the response type.
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"engine":"kokoro","voices":["af_heart"]}'
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: Response())
    result = CliRunner().invoke(cli, ["--list-voices"])
    assert result.exit_code == 0 and "af_heart" in result.output and "EN-US" in result.output
    monkeypatch.setattr(urllib.request, "urlopen", Mock(side_effect=URLError("offline")))
    result = CliRunner().invoke(cli, ["--list-voices"])
    assert result.exit_code == 0 and "Engine not running" in result.output
