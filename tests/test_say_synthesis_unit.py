"""Tests of the macOS say backend without invoking speech or audio devices."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.tts import say


@pytest.fixture
def engine(monkeypatch):
    instance = say.SayTTS(speed=900, voice='Samantha')
    monkeypatch.setattr(instance, 'is_available', lambda: True)
    return instance


def test_cache_hit_controls_playback(engine, monkeypatch, tmp_path):
    cached = tmp_path / 'cached.aiff'
    player = Mock()
    monkeypatch.setattr(say, 'cache_hit', lambda key: cached)
    monkeypatch.setattr(say, 'play_audio_native', player)
    assert engine.speak('hello', play=False)
    player.assert_not_called()
    assert engine.speak('hello', voice='ignored', play=True, volume=.4)
    player.assert_called_once_with(cached, timeout=120.0, volume=.4)
    assert engine.speed == 720


def test_generation_saves_and_removes_temporary_file(engine, monkeypatch, tmp_path):
    command = Mock(return_value=SimpleNamespace(returncode=0, stderr=b''))
    save = Mock(return_value=tmp_path / 'saved.aiff')
    evict, player = Mock(), Mock()
    monkeypatch.setattr(say, 'cache_hit', lambda key: None)
    monkeypatch.setattr(say.subprocess, 'run', command)
    monkeypatch.setattr(say, 'cache_save', save)
    monkeypatch.setattr(say, 'cache_evict', evict)
    monkeypatch.setattr(say, 'play_audio_native', player)
    assert engine.speak('hello', volume=.7)
    args = command.call_args.args[0]
    assert args[:3] == ['say', '-r', '720']
    assert args[-3:] == ['-v', 'Samantha', 'hello']
    assert not save.call_args.args[1].exists()
    player.assert_called_once_with(tmp_path / 'saved.aiff', timeout=120.0, volume=.7)
    evict.assert_called_once()


def test_failure_and_voice_listing(engine, monkeypatch):
    monkeypatch.setattr(say, 'cache_hit', lambda key: None)
    run = Mock(return_value=SimpleNamespace(returncode=1, stderr=b'error'))
    monkeypatch.setattr(say.subprocess, 'run', run)
    assert not engine.speak('hello')
    run.return_value = SimpleNamespace(stdout='Samantha  en_US  # US\nDaniel  en_GB  # UK\nSamantha  en_US  # duplicate\ninvalid')
    assert engine.list_voices() == ['Daniel', 'Samantha']
    run.side_effect = OSError('missing')
    assert engine.list_voices() == []
    assert not engine.speak('hello')
