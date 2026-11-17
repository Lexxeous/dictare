"""Discard and stop boundaries must not revive canceled capture work."""

import queue
import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import (
    AppState,
    DiscardCurrent,
    SetListening,
    SpeechEnded,
    SpeechStarted,
    TranscriptionCompleted,
)


@pytest.fixture
def engine():
    instance = DictareEngine(Config(), logger=MagicMock(), hotkey_enabled=False)
    instance.audio_manager = MagicMock()
    instance.audio_manager.sample_rate = 16000
    instance._state_manager.transition(AppState.LISTENING, force=True)
    yield instance
    instance._controller._cancel_transcription_watchdog()


@pytest.mark.parametrize("explicit_identity", [False, True])
def test_late_native_result_after_discard_and_resume_does_not_update_or_deliver(engine, explicit_identity):
    old = engine._capture_generation
    engine._stt = MagicMock()

    def late_result(*args, **kwargs):
        engine.discard_current_internal()
        engine._state_manager.transition(AppState.LISTENING, force=True)
        return MagicMock(text="canceled sentence", language="en")

    engine._stt.transcribe.side_effect = late_result
    kwargs = {"capture_generation": old} if explicit_identity else {}
    engine._transcribe_job(np.zeros(16000), None, engine._stt_generation, **kwargs)
    assert engine._last_text == ""
    assert engine._stats.count == 0
    engine._logger.log_transcription.assert_not_called()
    assert engine._controller._queue.empty()


def test_new_job_keeps_destination_and_capture_identity(engine):
    audio = np.zeros(16000)
    destination = MagicMock()
    engine._stt_worker = MagicMock()
    engine._stt_worker.is_alive.return_value = True
    engine.transcribe_and_process(audio, destination, engine._capture_generation)
    job = engine._stt_jobs.get_nowait()
    assert job[0] is audio
    assert job[1] is destination
    assert job[2] == engine._capture_generation


def test_queued_old_job_does_not_start_native_recognition(engine):
    old = engine._capture_generation
    engine.discard_current_internal()
    jobs = queue.Queue()
    jobs.put((np.zeros(16000), None, old))
    jobs.put(None)
    engine._stt = MagicMock()
    engine._stt_worker_loop(engine._stt_generation, jobs, False)
    engine._stt.transcribe.assert_not_called()


@pytest.mark.parametrize("event", [
    SpeechStarted(capture_generation=0),
    SpeechEnded(audio_data=np.zeros(16000), capture_generation=0),
    TranscriptionCompleted(text="old result", capture_generation=0),
])
def test_old_events_cannot_restart_stopped_capture(engine, event):
    engine.discard_current_internal()
    engine._state_manager.transition(AppState.OFF, force=True)
    engine.transcribe_and_process = MagicMock()
    engine.inject_text = MagicMock()
    engine._controller._handle_event(event)
    assert engine.state == AppState.OFF
    engine.transcribe_and_process.assert_not_called()
    engine.inject_text.assert_not_called()


def test_discard_clears_jobs_and_deferred_submit_but_preserves_shutdown(engine):
    engine._stt_jobs.put((np.zeros(16000), None, engine._capture_generation))
    engine._stt_jobs.put(None)
    engine._submit_pending = True
    engine.discard_current_internal()
    assert engine._stt_jobs.get_nowait() is None
    assert engine._stt_jobs.empty()
    assert engine._submit_pending is False


def test_old_delivery_is_rejected_before_control_executors(engine):
    engine._pipeline = MagicMock()
    old = engine._capture_generation
    engine.discard_current_internal()
    engine.inject_text("old control command", capture_generation=old)
    engine._pipeline.process.assert_not_called()


def test_old_timeout_does_not_cancel_new_watchdog_or_complete_new_recording(engine):
    old = engine._capture_generation
    engine.discard_current_internal()
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    watchdog = MagicMock()
    engine._controller._transcription_watchdog = watchdog
    engine._controller._on_transcription_timeout(capture_generation=old)
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert engine.state == AppState.TRANSCRIBING
    watchdog.cancel.assert_not_called()


def test_discard_during_transcription_cancels_pending_state_without_waiting(engine):
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    engine._controller._pending_transcription = TranscriptionCompleted(text="old")
    watchdog = MagicMock()
    engine._controller._transcription_watchdog = watchdog
    engine._controller._handle_event(DiscardCurrent())
    assert engine.state == AppState.LISTENING
    assert engine._controller._pending_transcription is None
    watchdog.cancel.assert_called_once()


def test_stop_then_start_rejects_old_completion(engine):
    old = engine._capture_generation
    engine.inject_text = MagicMock()
    engine._controller._handle_event(SetListening(on=False))
    assert engine.state == AppState.OFF
    engine._controller._handle_event(SetListening(on=True))
    engine._controller._handle_event(TranscriptionCompleted(text="old", capture_generation=old))
    assert engine.state == AppState.LISTENING
    engine.inject_text.assert_not_called()


def test_stop_finishes_current_sentence_then_invalidates_other_queued_capture(engine):
    old = engine._capture_generation
    engine.inject_text = MagicMock()
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    engine._controller._handle_event(SetListening(on=False))
    event = TranscriptionCompleted(text="current", capture_generation=old)
    engine._controller._handle_event(event)
    assert engine.state == AppState.OFF
    engine.inject_text.assert_called_once()
    engine._controller._handle_event(event)
    assert engine.state == AppState.OFF
    assert engine.inject_text.call_count == 1


def test_callback_finishing_during_vad_reset_keeps_old_identity(engine):
    engine.audio_manager.reset_vad.side_effect = lambda: engine._on_vad_speech_end(np.zeros(16000))
    engine.discard_current_internal()
    engine.transcribe_and_process = MagicMock()
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    engine.transcribe_and_process.assert_not_called()


def test_discard_serializes_with_delivery_and_blocks_later_old_work(engine):
    entered, release, discarding, discarded = (threading.Event() for _ in range(4))
    old = engine._capture_generation
    agent = MagicMock()

    def send(message):
        entered.set()
        assert release.wait(2)
        return True

    def discard():
        discarding.set()
        engine.discard_current_internal()
        discarded.set()

    agent.send.side_effect = send
    delivery = threading.Thread(target=engine.inject_text, args=("current",), kwargs={"agent": agent, "capture_generation": old})
    cancel = threading.Thread(target=discard)
    delivery.start()
    try:
        assert entered.wait(2)
        cancel.start()
        assert discarding.wait(2)
        assert not discarded.wait(0.05)
    finally:
        release.set()
        delivery.join(2)
        if cancel.ident is not None:
            cancel.join(2)
    assert not delivery.is_alive() and not cancel.is_alive()
    assert discarded.is_set()
    engine.inject_text("old", agent=agent, capture_generation=old)
    agent.send.assert_called_once()
