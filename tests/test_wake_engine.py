from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from pydantic import ValidationError

from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState, TranscriptionCompleted


def test_wake_gates_transcript_logging_and_submits_only_after_end():
    config = Config.model_validate({"hotkey": {"activation_mode": "wake", "wake_phrase": "hey dictare", "end_phrase": "finish prompt"}})
    logger = MagicMock()
    engine = DictareEngine(config, logger=logger, hotkey_enabled=False)
    engine._state_manager.transition(AppState.LISTENING, force=True)
    engine._stt = MagicMock()
    engine._stt.transcribe.side_effect = [
        SimpleNamespace(text="private conversation", language="en"),
        SimpleNamespace(text="hey dictare write this", language="en"),
        SimpleNamespace(text="carefully finish prompt ignored", language="en"),
    ]
    agent = MagicMock()
    for _ in range(3):
        engine._transcribe_job(np.zeros(8000), agent, engine._stt_generation)
    events = [engine._controller._queue.get_nowait() for _ in range(3)]
    assert [event.text for event in events] == ["", "", "write this carefully"]
    assert [event.submit for event in events] == [False, False, True]
    assert events[-1].agent is agent
    assert logger.log_transcription.call_count == 1
    assert logger.log_transcription.call_args.kwargs["text"] == "write this carefully"
    assert engine._last_text == "write this carefully"


def test_wake_buffer_is_discarded_when_destination_changes():
    config = Config.model_validate({"hotkey": {"activation_mode": "wake", "end_phrase": "finish prompt"}})
    engine = DictareEngine(config, hotkey_enabled=False)
    engine._state_manager.transition(AppState.LISTENING, force=True)
    engine._stt = MagicMock()
    engine._stt.transcribe.side_effect = [
        SimpleNamespace(text="hey dictare private prompt", language="en"),
        SimpleNamespace(text="finish prompt", language="en"),
    ]
    engine._transcribe_job(np.zeros(8000), MagicMock(), engine._stt_generation)
    engine._transcribe_job(np.zeros(8000), MagicMock(), engine._stt_generation)
    assert engine._controller._queue.get_nowait().text == ""
    assert engine._controller._queue.get_nowait().text == ""
    assert engine._last_text == ""


def test_end_phrase_delivers_submit_to_captured_agent():
    config = Config.model_validate({"hotkey": {"activation_mode": "wake", "end_phrase": "finish prompt"}})
    engine = DictareEngine(config, hotkey_enabled=False)
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    agent = MagicMock()
    agent.send.return_value = True
    engine._controller._handle_event(TranscriptionCompleted(text="write this", agent=agent, submit=True))
    message = agent.send.call_args.args[0]
    assert message["text"] == "write this"
    assert "submit" in message["x_input"]["ops"]


def test_wake_timeout_discards_partial_prompt_and_invalidates_capture():
    config = Config.model_validate({"hotkey": {"activation_mode": "wake", "end_phrase": "finish prompt"}})
    engine = DictareEngine(config, hotkey_enabled=False)
    engine._phrase_gate.accept("hey dictare private")
    generation = engine._capture_generation
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    engine._controller._handle_event(TranscriptionCompleted(text="", source="timeout", capture_generation=generation))
    assert not engine._phrase_gate.capturing
    assert not engine.capture_allowed(generation)


@pytest.mark.parametrize("hotkey", [
    {"wake_phrase": "okay stop"},
    {"end_phrase": "ok mute"},
    {"wake_phrase": "hey dictare", "end_phrase": "hey dictare now"},
    {"wake_phrase": "hello 世界"},
])
def test_wake_rejects_ambiguous_or_unsupported_phrases(hotkey):
    with pytest.raises(ValidationError):
        Config.model_validate({"hotkey": {"activation_mode": "wake", **hotkey}})


def test_wake_rejects_conflicts_with_personal_and_advanced_commands():
    with pytest.raises(ValidationError):
        Config.model_validate({"hotkey": {"activation_mode": "wake", "wake_phrase": "send now"},
                               "voice_commands": {"enabled": True, "send": "send now"}})
    with pytest.raises(ValidationError):
        Config.model_validate({"hotkey": {"activation_mode": "wake", "end_phrase": "finish this"},
                               "pipeline": {"submit_filter": {"triggers": {"*": [["finish|end", "this"]]}}}})
