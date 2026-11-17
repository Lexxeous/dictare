"""Canceled queue items do not begin playback or strand completion callbacks."""

import queue
import threading
from unittest.mock import MagicMock

import numpy as np

from dictare.audio import beep


def test_invalidation_skips_old_items_and_preserves_new_audio(monkeypatch):
    pending = queue.Queue()
    monkeypatch.setattr(beep, "_play_queue", pending)
    monkeypatch.setattr(beep, "_ensure_worker", lambda: None)
    monkeypatch.setattr(beep, "_sound_cache", {"old": (np.zeros(1), 16000), "new": (np.zeros(1), 16000)})
    device = MagicMock()
    device.get_stream.return_value = None
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", device)
    monkeypatch.setattr("dictare.audio.capture._run_with_timeout", lambda action, **kwargs: action())
    monkeypatch.setattr(beep, "_execute_audio_control", lambda label, action: action())
    completed = []
    beep.play_sound_file("old", on_complete=lambda: completed.append("old"))
    beep.cancel_pending_feedback()
    beep.play_sound_file("new", on_complete=lambda: completed.append("new"))
    pending.put(None)
    beep._audio_worker()
    assert completed == ["old", "new"]
    assert device.play.call_count == 1


def test_cancellation_before_owner_executes_prevents_native_start(monkeypatch):
    pending = queue.Queue()
    monkeypatch.setattr(beep, "_play_queue", pending)
    monkeypatch.setattr(beep, "_ensure_worker", lambda: None)
    monkeypatch.setattr(beep, "_sound_cache", {"sound": (np.zeros(1), 16000)})
    device = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", device)
    monkeypatch.setattr("dictare.audio.capture._run_with_timeout", lambda action, **kwargs: action())
    def execute(label, action):
        beep.cancel_pending_feedback()
        return action()
    monkeypatch.setattr(beep, "_execute_audio_control", execute)
    completed = MagicMock()
    beep.play_sound_file("sound", on_complete=completed)
    pending.put(None)
    beep._audio_worker()
    device.play.assert_not_called()
    completed.assert_called_once()


def test_cancelled_synchronous_wav_reports_failure(monkeypatch):
    pending = queue.Queue()
    monkeypatch.setattr(beep, "_play_queue", pending)
    monkeypatch.setattr(beep, "_ensure_worker", lambda: None)
    result = []
    worker = threading.Thread(target=lambda: result.append(beep.play_wav_sync("old", timeout_s=2)))
    worker.start()
    item = pending.get(timeout=1)
    pending.put(item)
    beep.cancel_pending_feedback()
    pending.put(None)
    beep._audio_worker()
    worker.join(timeout=2)
    assert result == [False]


def test_suspended_feedback_rejects_new_items_and_completes_callbacks(monkeypatch):
    pending = queue.Queue()
    monkeypatch.setattr(beep, "_play_queue", pending)
    monkeypatch.setattr(beep, "_ensure_worker", lambda: None)
    stop = MagicMock()
    monkeypatch.setattr(beep, "stop_portaudio_output", stop)
    completed = MagicMock()
    try:
        beep.suspend_feedback()
        beep.play_sound_file("blocked", on_complete=completed)
        beep.start_loop("blocked")
        assert pending.empty()
        assert not beep.is_looping()
        completed.assert_called_once()
        stop.assert_called_once()
        assert not beep.play_wav_sync("blocked", timeout_s=0.1)
    finally:
        beep.resume_feedback()


def test_suspension_terminates_active_fallback_player(monkeypatch):
    monkeypatch.setattr(beep.sys, "platform", "darwin")
    monkeypatch.setattr(beep, "stop_portaudio_output", lambda: None)
    started = threading.Event()
    stopped = threading.Event()
    process = MagicMock()
    process.wait.side_effect = lambda **kw: stopped.wait(timeout=2)
    process.terminate.side_effect = stopped.set
    def popen(*args, **kwargs):
        started.set()
        return process
    monkeypatch.setattr(beep.subprocess, "Popen", popen)
    generation = beep._play_generation
    worker = threading.Thread(target=beep._play_sound_file_fallback, args=("test.wav", generation))
    try:
        worker.start()
        assert started.wait(timeout=2)
        beep.suspend_feedback()
        assert stopped.wait(timeout=2)
    finally:
        beep.resume_feedback()
        worker.join(timeout=2)
    assert not worker.is_alive()
