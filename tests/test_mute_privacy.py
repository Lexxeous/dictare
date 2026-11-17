"""Mute must gate capture before recognition and reject work across quick resume."""

from __future__ import annotations

import queue
from unittest.mock import MagicMock

import numpy as np
import pytest

from dictare.app.controller import _ControllerEvents
from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import (
    AppState,
    PrivacyMuted,
    SetListening,
    SpeechEnded,
    SpeechStarted,
    TranscriptionCompleted,
)


@pytest.fixture
def engine(monkeypatch):
    engine = DictareEngine(Config(), logger=MagicMock(), hotkey_enabled=False)
    engine.audio_manager = MagicMock()
    engine.audio_manager.sample_rate = 16000
    engine.tts_mgr = MagicMock()
    monkeypatch.setattr("dictare.audio.beep.stop_loop", MagicMock())
    engine._state_manager.transition(AppState.LISTENING, force=True)
    return engine


def test_muted_audio_callbacks_do_not_log_or_queue_work(engine):
    engine.mute()
    engine._logger.reset_mock()
    engine._on_vad_speech_start()
    engine._on_vad_speech_end(np.zeros(16000))
    engine.transcribe_and_process(np.zeros(16000))
    assert engine._stt_jobs.empty()
    assert isinstance(engine._controller._queue.get_nowait(), PrivacyMuted)
    assert engine._controller._queue.empty()
    engine._logger.log_vad_event.assert_not_called()
    engine.tts_mgr.speak_text.assert_not_called()
    engine.tts_mgr.stop_speaking.assert_called_once()


def test_audio_manager_does_not_feed_vad_while_capture_gate_is_closed(engine):
    from dictare.core.audio_manager import AudioManager

    audio = AudioManager(engine.config.audio)
    audio._streaming_vad = MagicMock()
    audio._is_running_check = lambda: True
    audio._should_process_check = engine.capture_allowed
    engine.mute()
    audio.on_audio_chunk(np.zeros(512))
    audio._streaming_vad.process_chunk.assert_not_called()
    engine.unmute()
    audio.on_audio_chunk(np.zeros(512))
    audio._streaming_vad.process_chunk.assert_called_once()


def test_mute_releases_queued_audio_but_preserves_shutdown_sentinel(engine):
    engine._stt_jobs.put((np.zeros(16000), None, engine._capture_generation))
    engine._stt_jobs.put(None)
    engine.mute()
    assert engine._stt_jobs.get_nowait() is None
    assert engine._stt_jobs.empty()


def test_native_result_returning_after_mute_and_resume_is_discarded(engine):
    old_capture = engine._capture_generation
    stt = MagicMock()

    def late_result(*args, **kwargs):
        engine.mute()
        engine.unmute()
        return MagicMock(text="private conversation", language="en")

    stt.transcribe.side_effect = late_result
    engine._stt = stt
    engine._transcribe_job(np.zeros(16000), None, engine._stt_generation, old_capture)
    assert engine._last_text == ""
    assert engine._stats.count == 0
    engine._logger.log_transcription.assert_not_called()
    events = []
    while not engine._controller._queue.empty():
        events.append(engine._controller._queue.get_nowait())
    assert not any(isinstance(event, TranscriptionCompleted) for event in events)


def test_queued_jobs_from_before_mute_do_not_start_after_resume(engine):
    old_capture = engine._capture_generation
    jobs = queue.Queue()
    jobs.put((np.zeros(16000), None, old_capture))
    jobs.put(None)
    engine._stt = MagicMock()
    engine.mute()
    engine.unmute()
    engine._stt_worker_loop(engine._stt_generation, jobs, False)
    engine._stt.transcribe.assert_not_called()


@pytest.mark.parametrize("event", [
    SpeechStarted(capture_generation=0),
    SpeechEnded(audio_data=np.zeros(16000), capture_generation=0),
    TranscriptionCompleted(text="stale result", capture_generation=0),
])
def test_stale_events_cannot_restart_capture_or_inject_after_resume(engine, event):
    engine.mute()
    engine.unmute()
    engine.transcribe_and_process = MagicMock()
    engine.inject_text = MagicMock()
    engine._state_manager.transition(AppState.OFF, force=True)
    engine._controller._handle_event(event)
    assert engine.state == AppState.OFF
    engine.transcribe_and_process.assert_not_called()
    engine.inject_text.assert_not_called()


def test_delivery_gate_rejects_muted_and_pre_mute_text(engine):
    engine._pipeline = MagicMock()
    old_capture = engine._capture_generation
    engine.mute()
    engine.inject_text("muted text")
    engine.unmute()
    engine.inject_text("old text", capture_generation=old_capture)
    engine._pipeline.process.assert_not_called()


def test_old_watchdog_cannot_complete_a_new_capture_after_resume(engine):
    generation = engine._capture_generation
    engine.mute()
    engine.unmute()
    while not engine._controller._queue.empty():
        engine._controller._queue.get_nowait()
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    engine._controller._on_transcription_timeout(capture_generation=generation)
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert engine.state == AppState.TRANSCRIBING


def test_privacy_event_cancels_controller_work_and_explicit_start_resumes(engine):
    engine._controller._pending_transcription = TranscriptionCompleted(text="private")
    engine.mute()
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert engine.state == AppState.OFF
    assert engine._controller._pending_transcription is None
    engine._controller._handle_event(SetListening(on=True))
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert engine.state == AppState.LISTENING
    assert engine.capture_allowed()


def test_muted_status_is_steady_and_not_active(engine):
    engine.mute()
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    status = engine.get_status()
    assert status["platform"]["state"] == "muted"
    assert status["stt"]["active"] is False


def test_muted_state_changes_do_not_play_capture_feedback(engine, monkeypatch):
    play = MagicMock()
    monkeypatch.setattr("dictare.audio.beep.play_audio", play)
    monkeypatch.setattr("dictare.audio.beep.play_sound_file_async", play)
    monkeypatch.setattr("dictare.audio.beep.start_loop", play)
    engine.mute()
    events = _ControllerEvents(engine.config)
    events.set_engine(engine)
    events.on_state_change(AppState.TRANSCRIBING, AppState.LISTENING, "transcription_complete")
    engine._play_focus_gated_sound("transcribed")
    play.assert_not_called()
