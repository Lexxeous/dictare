"""Normal operational logs must not retain recognized or spoken content."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from dictare.config import Config
from dictare.core.openvip_messages import create_message
from dictare.core.tts_manager import TTSManager
from dictare.pipeline.executors.mute import MuteExecutor
from dictare.pipeline.filters.input_filter import InputFilter
from dictare.pipeline.filters.mute_filter import MuteFilter
from dictare.tts.proxy import WorkerTTSEngine


@pytest.mark.parametrize("action", ["mute", "listen", "send"])
@pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
def test_command_logs_hide_intervening_speech_unless_debug(caplog, action, level):
    caplog.set_level(level, logger="dictare")
    text = f"ok confidential {action}"
    if action == "send":
        step = InputFilter(triggers={"*": [["ok", "send"]]})
    else:
        step = MuteFilter(
            mute_triggers={"*": [["ok", "mute"]]},
            listen_triggers={"*": [["ok", "listen"]]},
            is_muted=lambda: action == "listen",
        )
    result = step.process(create_message(text))
    assert result.messages
    if action != "send":
        called = []
        executor = MuteExecutor(mute_fn=lambda: called.append("mute"), unmute_fn=lambda: called.append("listen"))
        executor.process(result.messages[0])
        assert called == [action]
    records = [record.__dict__ for record in caplog.records]
    assert records
    assert ("confidential" in str(records)) == (level == logging.DEBUG)


@pytest.mark.parametrize("state", ["unloaded", "load_error", "success", "failure", "exception"])
def test_tts_manager_logs_metadata_without_spoken_text(caplog, state):
    caplog.set_level(logging.INFO, logger="dictare")
    manager = TTSManager(Config())
    text = "confidential spoken sentence"
    backend = MagicMock()
    if state == "load_error":
        manager._tts_error = "backend unavailable"
    elif state != "unloaded":
        manager._tts_engine = backend
        backend.speak.return_value = state == "success"
        if state == "exception":
            backend.speak.side_effect = RuntimeError("backend failed")
    with patch("dictare.audio.beep.play_audio", side_effect=lambda callback, **kwargs: callback()):
        manager.speak_text(text)
    assert text not in caplog.text
    assert caplog.records
    if state not in {"unloaded", "load_error"}:
        assert backend.speak.call_args.args[0] == text


@pytest.mark.parametrize("delivered", [False, True])
def test_tts_proxy_failure_logs_exclude_spoken_text(caplog, delivered):
    caplog.set_level(logging.INFO, logger="dictare")
    server = MagicMock()
    server.put_message.return_value = delivered
    proxy = WorkerTTSEngine(server)
    text = "confidential worker sentence"
    with patch("dictare.tts.proxy._SPEAK_TIMEOUT", 0):
        assert proxy.speak(text) is False
    assert text not in caplog.text
    assert caplog.records
    assert server.put_message.call_args.args[1]["text"] == text
