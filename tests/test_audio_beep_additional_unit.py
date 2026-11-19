"""Exercise audio feedback fallbacks without starting audio devices."""
import subprocess
from unittest.mock import Mock

import numpy as np

from dictare.audio import beep


def test_loop_chunks_sound_at_sample_rate_and_applies_volume(monkeypatch):
    cache = {'song': (np.array([2., 4., 6., 8., 10.]), 2)}
    monkeypatch.setattr(beep, '_sound_cache', cache)
    monkeypatch.setattr(beep, '_loop_chunk_keys', [])
    monkeypatch.setattr(beep, '_loop_chunk_pos', 0)
    monkeypatch.setattr(beep, '_loop_volume', 0.5)
    monkeypatch.setattr(beep, '_ensure_worker', Mock())
    enqueue = Mock()
    monkeypatch.setattr(beep, '_enqueue_sound', enqueue)
    beep._loop_active.set()
    try:
        beep._start_loop_now('song')
        assert beep._loop_chunk_keys == ['__loop_chunk_0__', '__loop_chunk_1__', '__loop_chunk_2__']
        np.testing.assert_array_equal(cache['__loop_chunk_0__'][0], [1., 2.])
        enqueue.assert_called_once_with('__loop_chunk_0__', 1.0, beep._enqueue_loop_next)
        beep._enqueue_loop_next()
        assert enqueue.call_args.args[0] == '__loop_chunk_1__'
    finally:
        beep._loop_active.clear()


def test_fallback_tries_next_player_when_first_is_missing(monkeypatch):
    process = Mock()
    popen = Mock(side_effect=[FileNotFoundError(), process])
    monkeypatch.setattr(beep.sys, 'platform', 'linux')
    monkeypatch.setattr(beep.subprocess, 'Popen', popen)
    monkeypatch.setattr(beep, '_feedback_suspended', False)
    beep._play_sound_file_fallback('sound.wav', beep._play_generation)
    assert [call.args[0] for call in popen.call_args_list] == [['paplay', 'sound.wav'], ['aplay', '-q', 'sound.wav']]
    process.wait.assert_called_once_with(timeout=beep._FALLBACK_CMD_TIMEOUT)
    assert beep._fallback_process is None


def test_fallback_terminates_timed_out_player(monkeypatch):
    process = Mock()
    process.wait.side_effect = [subprocess.TimeoutExpired('player', 5), None]
    monkeypatch.setattr(beep.subprocess, 'Popen', lambda *a, **kw: process)
    monkeypatch.setattr(beep, '_feedback_suspended', False)
    beep._play_sound_file_fallback('sound.wav', beep._play_generation)
    process.terminate.assert_called_once_with()
    assert process.wait.call_count == 2
    assert beep._fallback_process is None
