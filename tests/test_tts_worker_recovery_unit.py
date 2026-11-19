"""Worker recovery and playback behavior without a server or audio hardware."""
import io
import sys
import threading
import types
import urllib.error
from pathlib import Path
from unittest.mock import Mock

import pytest

from dictare.tts import worker


@pytest.mark.parametrize('cached,play_raises,speak_raises', [(True, False, False), (True, True, False), (False, False, True)])
def test_worker_reports_playback_failures(monkeypatch, tmp_path, cached, play_raises, speak_raises):
    import dictare.tts as tts
    import dictare.tts.base as base
    import dictare.utils.paths as paths

    class Speech:
        id = 'message'
        text = 'hello'
        voice = 'voice'
        language = 'en'

    class ImmediateThread:
        def __init__(self, *, target, args=(), **kwargs):
            self.target, self.args = target, args
        def start(self):
            if self.target.__name__ == '_play_cached_thread':
                self.target(*self.args)

    engine = Mock()
    engine.get_name.return_value = 'fake'
    engine.check_cache.return_value = Path('/tmp/cached.wav') if cached else None
    engine.speak.side_effect = RuntimeError('synthesis failed') if speak_raises else None
    player = Mock(side_effect=RuntimeError('playback failed') if play_raises else None, return_value=True)
    client = Mock()
    client.subscribe.return_value = iter([Speech()])
    monkeypatch.setitem(sys.modules, 'openvip', types.SimpleNamespace(Client=lambda *a, **k: client))
    monkeypatch.setitem(sys.modules, 'openvip.models.speech_request', types.SimpleNamespace(SpeechRequest=Speech))
    monkeypatch.setattr(paths, 'get_data_dir', lambda: tmp_path)
    monkeypatch.setattr(tts, 'create_tts_engine', lambda config: engine)
    monkeypatch.setattr(base, 'play_audio_native', player)
    monkeypatch.setattr(threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(worker, '_playback_permitted', lambda *a: True)
    completion = Mock()
    monkeypatch.setattr(worker, '_post_completion', completion)
    monkeypatch.setenv('DICTARE_TTS_TOKEN', 'token')
    worker.main(['--engine', 'say', '--parent-pid', '123'])
    assert completion.call_args.args[2:4] == ('message', not (play_raises or speak_raises))
    assert player.called is cached


def test_disconnect_exits_after_three_forbidden_responses(monkeypatch, tmp_path):
    import dictare.tts as tts
    import dictare.utils.paths as paths

    class Speech:
        pass

    client = Mock()
    def subscribe(*args, **kwargs):
        error = urllib.error.HTTPError('http://engine', 403, 'forbidden', {}, None)
        kwargs['on_disconnect'](error)
        kwargs['on_connect']()
        kwargs['on_disconnect'](error)
        kwargs['on_disconnect'](OSError('disconnected'))
        for _ in range(3):
            kwargs['on_disconnect'](error)
        return iter(())
    client.subscribe.side_effect = subscribe
    monkeypatch.setitem(sys.modules, 'openvip', types.SimpleNamespace(Client=lambda *a, **k: client))
    monkeypatch.setitem(sys.modules, 'openvip.models.speech_request', types.SimpleNamespace(SpeechRequest=Speech))
    monkeypatch.setattr(paths, 'get_data_dir', lambda: tmp_path)
    monkeypatch.setattr(tts, 'create_tts_engine', lambda config: Mock())
    monkeypatch.setattr(threading, 'Thread', Mock())
    monkeypatch.setenv('DICTARE_TTS_TOKEN', 'token')
    with pytest.raises(SystemExit) as exc:
        worker.main(['--engine', 'say'])
    assert exc.value.code == 0


def test_parent_watcher_stops_audio_before_exit(monkeypatch):
    import dictare.tts.base as base
    stop = Mock()
    monkeypatch.setattr(base, 'stop_audio_native', stop)
    monkeypatch.setattr(worker.os, 'getppid', lambda: 7)
    exit_worker = Mock(side_effect=SystemExit(0))
    monkeypatch.setattr(worker.os, '_exit', exit_worker)
    with pytest.raises(SystemExit):
        worker._watch_parent(8)
    stop.assert_called_once_with()
    exit_worker.assert_called_once_with(0)


def test_interrupt_ack_loop_consumes_request(monkeypatch):
    import time
    ack = Mock()
    monkeypatch.setattr(worker, '_acknowledge_interruption', ack)
    monkeypatch.setattr(worker, '_interrupt_ack_requested', True)
    monkeypatch.setattr(time, 'sleep', Mock(side_effect=StopIteration))
    with pytest.raises(StopIteration):
        worker._interrupt_ack_loop('url', 'token')
    ack.assert_called_once_with('url', 'token')
    assert not worker._interrupt_ack_requested


def test_failed_notifications_are_logged(monkeypatch, caplog):
    monkeypatch.setattr(worker.urllib.request, 'urlopen', Mock(side_effect=OSError('offline')))
    worker._post_completion('http://engine', 'token', 'id', False)
    worker._acknowledge_interruption('http://engine', 'token')
    assert 'Failed to post TTS completion' in caplog.text
    assert 'Failed to acknowledge TTS interruption' in caplog.text


def test_interrupt_without_id_does_not_stop_audio(monkeypatch):
    import dictare.tts.base as base
    stop = Mock()
    monkeypatch.setattr(base, 'stop_audio_native', stop)
    monkeypatch.setattr(worker.urllib.request, 'urlopen', Mock(return_value=io.BytesIO(b'{}')))
    worker._acknowledge_interruption('http://engine', 'token')
    stop.assert_not_called()
