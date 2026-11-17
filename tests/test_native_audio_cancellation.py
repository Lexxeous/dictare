"""Native speech players are all stopped and stale synthesis cannot play later."""

import threading
from unittest.mock import MagicMock

from dictare.tts import base


def test_suspend_stops_all_parallel_players_and_blocks_new_ones(monkeypatch):
    monkeypatch.setattr(base.sys, "platform", "darwin")
    started = [threading.Event(), threading.Event()]
    stopped = [threading.Event(), threading.Event()]
    processes = []

    def popen(*args, **kwargs):
        index = len(processes)
        proc = MagicMock()
        proc.wait.side_effect = lambda **kw: stopped[index].wait(timeout=2)
        proc.terminate.side_effect = stopped[index].set
        processes.append(proc)
        started[index].set()
        return proc

    monkeypatch.setattr(base.subprocess, "Popen", popen)
    threads = [threading.Thread(target=base.play_audio_native, args=("test.wav",)) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        assert all(event.wait(timeout=2) for event in started)
        base.suspend_native_audio()
        assert all(event.wait(timeout=2) for event in stopped)
        assert not base.play_audio_native("blocked.wav")
        assert len(processes) == 2
    finally:
        base.resume_native_audio()
        for thread in threads:
            thread.join(timeout=2)
    assert all(not thread.is_alive() for thread in threads)


def test_old_synthesis_generation_remains_invalid_after_resume(monkeypatch):
    monkeypatch.setattr(base.sys, "platform", "darwin")
    process = MagicMock()
    popen = MagicMock(return_value=process)
    monkeypatch.setattr(base.subprocess, "Popen", popen)
    old = base.native_audio_generation()
    base.suspend_native_audio()
    during_mute = base.native_audio_generation()
    base.resume_native_audio()
    with base.native_audio_scope(during_mute):
        assert not base.play_audio_native("started-muted.wav")
    with base.native_audio_scope(old):
        assert not base.play_audio_native("stale.wav")
    popen.assert_not_called()
    with base.native_audio_scope(base.native_audio_generation()):
        assert base.play_audio_native("fresh.wav")
    popen.assert_called_once()


def test_revoked_worker_permit_blocks_player_before_and_after_spawn(monkeypatch):
    monkeypatch.setattr(base.sys, "platform", "darwin")
    process = MagicMock()
    popen = MagicMock(return_value=process)
    monkeypatch.setattr(base.subprocess, "Popen", popen)
    with base.native_playback_permit(lambda: False):
        assert not base.play_audio_native("blocked.wav")
    popen.assert_not_called()
    permits = iter([True, False])
    with base.native_playback_permit(lambda: next(permits)):
        assert not base.play_audio_native("revoked.wav")
    process.terminate.assert_called_once()
