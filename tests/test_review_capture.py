"""Capture is paused and stale work rejected while a prompt awaits review."""

import asyncio
from unittest.mock import Mock

from dictare.agent.sse import SSEAgent
from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState, HotkeyPressed, SetListening, TranscriptionCompleted


def test_review_pauses_capture_and_blocks_resume_until_discard():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine._review_enabled = True
    queue = asyncio.Queue()
    agent = SSEAgent("codex", Mock(), queue=queue)
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    generation = engine._capture_generation
    engine._controller._handle_event(TranscriptionCompleted(
        text="hello", agent=agent, source="stt", capture_generation=generation,
    ))
    draft = engine.review_snapshot()
    assert draft is not None and draft.messages[0]["text"] == "hello"
    assert engine.send_review(draft.id) == "unavailable"
    assert not engine.discard_review(draft.id)
    assert not engine.capture_allowed(generation)
    engine._submit_action()
    agent._server.put_message.assert_not_called()
    # The state controller applies the queued stop after the current event.
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert engine._state_manager.state == AppState.OFF
    engine._controller._handle_event(HotkeyPressed(source="test"))
    engine._controller._handle_event(SetListening(on=True, source="test"))
    assert engine._state_manager.state == AppState.OFF
    assert engine.discard_review(draft.id)
    assert engine._state_manager.state == AppState.OFF
    engine._controller._handle_event(SetListening(on=True, source="test"))
    assert engine._state_manager.state == AppState.LISTENING
    assert not engine.capture_allowed(generation)


def test_review_retains_unbound_destinations_without_sending():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine._review_enabled = True
    agent = Mock()
    agent.id = "keyboard"
    engine.inject_text("private", agent=agent)
    agent.send.assert_not_called()
    draft = engine.review_snapshot()
    assert draft is not None and draft.messages[0]["text"] == "private"
    assert engine.send_review(draft.id) == "failed"
    assert engine.review_snapshot().id == draft.id


def test_restart_and_shutdown_do_not_discard_pending_draft():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine._review_enabled = True
    engine.inject_text("private", agent=None)
    draft = engine.review_snapshot()
    assert draft is not None
    for command in ("engine.restart", "engine.shutdown", "stt.start", "stt.toggle"):
        result = engine.handle_protocol_command({"command": command})
        assert result["status"] == "error"
        assert engine.review_snapshot().id == draft.id


def test_capture_after_protocol_exit_request_is_not_delivered():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    target = Mock()
    target.id = "codex"
    engine.requested_exit_reason = "protocol_restart"
    engine.inject_text("late result", agent=target)
    target.send.assert_not_called()
    assert engine.review_snapshot() is None


def test_submit_only_command_does_not_create_a_review_draft():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    engine._review_enabled = True
    target = Mock()
    target.id = "codex"
    target.send.return_value = True
    engine._pipeline = Mock()
    engine._pipeline.process.return_value = [{"text": "", "x_input": {"ops": ["submit"]}}]
    engine._executor_pipeline = None
    engine.inject_text("send command", agent=target)
    assert engine.review_snapshot() is None
    target.send.assert_called_once()


def test_pending_review_stops_audio_before_vad():
    import numpy as np

    from dictare.core.audio_manager import AudioManager
    from dictare.core.prompt_review import UnavailableReviewAgent

    config = Config()
    config.output.mode = "keyboard"
    engine = DictareEngine(config, hotkey_enabled=False)
    engine._state_manager.transition(AppState.LISTENING, force=True)
    audio = AudioManager(config.audio)
    audio._streaming_vad = Mock()
    audio._is_running_check = lambda: True
    audio._should_process_check = engine._should_process_capture
    audio.on_audio_chunk(np.zeros(512))
    audio._streaming_vad.process_chunk.assert_called_once()
    engine._review_slot.hold(UnavailableReviewAgent("keyboard"), [{"text": "pending"}])
    audio._streaming_vad.process_chunk.reset_mock()
    audio.on_audio_chunk(np.zeros(512))
    audio._streaming_vad.process_chunk.assert_not_called()


def test_audio_that_waited_for_vad_lock_is_rechecked_after_review_starts():
    import threading

    import numpy as np

    from dictare.core.audio_manager import AudioManager
    from dictare.core.prompt_review import UnavailableReviewAgent

    config = Config()
    config.output.mode = "keyboard"
    engine = DictareEngine(config, hotkey_enabled=False)
    engine._state_manager.transition(AppState.LISTENING, force=True)
    audio = AudioManager(config.audio)
    audio._streaming_vad = Mock()
    audio._is_running_check = lambda: True
    checked = threading.Event()

    def check():
        result = engine._should_process_capture()
        checked.set()
        return result

    audio._should_process_check = check
    with audio._vad_lock:
        worker = threading.Thread(target=audio.on_audio_chunk, args=(np.zeros(512),))
        worker.start()
        assert checked.wait(timeout=2)
        engine._review_slot.hold(UnavailableReviewAgent("keyboard"), [{"text": "pending"}])
    worker.join(timeout=2)
    assert not worker.is_alive()
    audio._streaming_vad.process_chunk.assert_not_called()
