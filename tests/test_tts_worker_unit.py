"""Exercise worker protocol and dispatch without starting audio or a server."""
import io
import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

from dictare.tts import worker


def test_completion_posts_authenticated_result(monkeypatch):
    send = Mock(return_value=io.BytesIO(b'ok'))
    monkeypatch.setattr(worker.urllib.request, 'urlopen', send)
    worker._post_completion('http://engine', 'secret', 'message', True, 42)
    request = send.call_args.args[0]
    assert request.full_url == 'http://engine/internal/tts/complete'
    assert request.get_header('Authorization') == 'Bearer secret'
    assert json.loads(request.data) == {'message_id': 'message', 'ok': True, 'duration_ms': 42}


def test_playback_permission_is_fail_closed_and_escapes_identifier(monkeypatch):
    send = Mock(return_value=io.BytesIO(b'{"allowed": true}'))
    monkeypatch.setattr(worker.urllib.request, 'urlopen', send)
    assert worker._playback_permitted('http://engine/', 'token', 'a/b')
    assert send.call_args.args[0].full_url.endswith('/permit/a%2Fb')
    send.side_effect = OSError('offline')
    assert not worker._playback_permitted('http://engine', 'token', 'a')


@pytest.mark.parametrize('stopped,expected_calls', [(True, 2), (False, 1)])
def test_interrupt_ack_waits_for_audio_to_stop(monkeypatch, stopped, expected_calls):
    import dictare.tts.base as base
    send = Mock(side_effect=lambda *a, **k: io.BytesIO(b'{"interrupt_id": "i1"}'))
    stop = Mock(return_value=stopped)
    monkeypatch.setattr(worker.urllib.request, 'urlopen', send)
    monkeypatch.setattr(base, 'stop_audio_native', stop)
    worker._acknowledge_interruption('http://engine/', 'token')
    stop.assert_called_once_with(wait=True)
    assert send.call_count == expected_calls
    if stopped:
        assert json.loads(send.call_args.args[0].data) == {'interrupt_id': 'i1'}


def test_stop_signal_requests_ack_and_stops_audio(monkeypatch):
    import dictare.tts.base as base
    stop = Mock()
    monkeypatch.setattr(base, 'stop_audio_native', stop)
    monkeypatch.setattr(worker, '_stop_requested', False)
    monkeypatch.setattr(worker, '_interrupt_ack_requested', False)
    worker._handle_stop_signal(0, None)
    assert worker._stop_requested and worker._interrupt_ack_requested
    stop.assert_called_once()


def test_main_requires_token(monkeypatch, capsys):
    monkeypatch.delenv('DICTARE_TTS_TOKEN', raising=False)
    with pytest.raises(SystemExit) as error:
        worker.main(['--engine', 'say'])
    assert error.value.code == 2
    assert 'DICTARE_TTS_TOKEN' in capsys.readouterr().err


def test_main_dispatches_speech_and_posts_results(monkeypatch, tmp_path):
    import threading

    import dictare.tts as tts
    import dictare.utils.paths as paths

    class Speech:
        def __init__(self, identifier, text):
            self.id, self.text = identifier, text
            self.voice, self.language = 'voice', 'en'

    messages = [types.SimpleNamespace(type='other'), Speech('1', 'speak'), Speech('2', 'denied'), Speech('3', 'cached')]
    engine = Mock()
    engine.get_name.return_value = 'fake'
    engine.check_cache.side_effect = [None, Path('/tmp/cached.wav')]
    engine.speak.return_value = True
    client = Mock()
    client.subscribe.return_value = iter(messages)
    monkeypatch.setitem(sys.modules, 'openvip', types.SimpleNamespace(Client=Mock(return_value=client)))
    monkeypatch.setitem(sys.modules, 'openvip.models.speech_request', types.SimpleNamespace(SpeechRequest=Speech))
    monkeypatch.setattr(paths, 'get_data_dir', lambda: tmp_path)
    monkeypatch.setattr(tts, 'create_tts_engine', lambda config: engine)
    monkeypatch.setenv('DICTARE_TTS_TOKEN', 'token')
    monkeypatch.setattr(threading, 'Thread', Mock())
    monkeypatch.setattr(worker, '_playback_permitted', lambda url, token, msg: msg != '2')
    completion = Mock()
    monkeypatch.setattr(worker, '_post_completion', completion)
    worker.main(['--engine', 'say'])
    engine.speak.assert_called_once_with('speak', voice='voice', language='en')
    assert completion.call_count == 2
    assert completion.call_args_list[0].args[2:4] == ('1', True)
    assert completion.call_args_list[1].args[2:4] == ('2', False)
    assert threading.Thread.call_count == 2
