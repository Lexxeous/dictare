"""Kokoro model acquisition and synthesis with external services isolated."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.tts import cache, kokoro


def test_model_download_skips_existing_files(monkeypatch, tmp_path):
    import urllib.request
    (tmp_path / 'model.onnx').touch()
    retrieve = Mock()
    monkeypatch.setattr(urllib.request, 'urlretrieve', retrieve)
    kokoro.KokoroTTS._download_model(tmp_path)
    retrieve.assert_called_once()
    assert retrieve.call_args.args[0].endswith('/voices-v1.0.bin')
    assert retrieve.call_args.args[1] == str(tmp_path / 'voices.bin')


def test_model_lazy_initialization_and_voice_listing(monkeypatch, tmp_path):
    model = SimpleNamespace(voices={'z': 1, 'a': 2})
    constructor = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, 'kokoro_onnx', SimpleNamespace(Kokoro=constructor))
    engine = kokoro.KokoroTTS()
    monkeypatch.setattr(engine, '_model_dir', lambda: tmp_path)
    download = Mock()
    monkeypatch.setattr(engine, '_download_model', download)
    assert engine.list_voices() == ['a', 'z']
    assert engine._get_kokoro() is model
    constructor.assert_called_once_with(str(tmp_path / 'model.onnx'), str(tmp_path / 'voices.bin'))
    download.assert_called_once_with(tmp_path)


def test_speak_uses_cached_audio(monkeypatch):
    engine = kokoro.KokoroTTS()
    engine._available = True
    monkeypatch.setattr(cache, 'cache_hit', lambda key: Path('/cached.wav'))
    play = Mock()
    monkeypatch.setattr(kokoro, 'play_audio_native', play)
    assert engine.speak('hello', volume=0.3)
    play.assert_called_once_with(Path('/cached.wav'), timeout=120.0, volume=0.3)


@pytest.mark.parametrize('fallback_cached', [False, True])
def test_failed_voice_falls_back_and_caches_synthesis(monkeypatch, fallback_cached, tmp_path):
    engine = kokoro.KokoroTTS()
    engine._available = True
    model = Mock()
    model.create.side_effect = [ValueError('bad voice'), ([0.1, 0.2], 24000)]
    monkeypatch.setattr(engine, '_get_kokoro', lambda: model)
    monkeypatch.setattr(cache, 'cache_hit', Mock(side_effect=[None, Path('/fallback.wav') if fallback_cached else None]))
    save = Mock(return_value=Path('/saved.wav'))
    monkeypatch.setattr(cache, 'cache_save', save)
    evict = Mock()
    monkeypatch.setattr(cache, 'cache_evict', evict)
    play = Mock()
    monkeypatch.setattr(kokoro, 'play_audio_native', play)
    import soundfile
    write = Mock()
    monkeypatch.setattr(soundfile, 'write', write)
    assert engine.speak('hello', voice='af_missing')
    assert model.create.call_args_list[0].kwargs['voice'] == 'af_missing'
    if fallback_cached:
        assert model.create.call_count == 1
        play.assert_called_once_with(Path('/fallback.wav'), timeout=120.0, volume=1.0)
    else:
        assert model.create.call_count == 2
        assert model.create.call_args.kwargs['voice'] == 'af_heart'
        assert not Path(write.call_args.args[0]).exists()
        save.assert_called_once()
        evict.assert_called_once()


def test_speak_failure_and_unavailable(monkeypatch):
    engine = kokoro.KokoroTTS()
    engine._available = False
    assert not engine.speak('hello')
    engine._available = True
    monkeypatch.setattr(cache, 'cache_hit', lambda key: None)
    monkeypatch.setattr(engine, '_get_kokoro', Mock(side_effect=RuntimeError('broken')))
    assert not engine.speak('hello')
    assert engine.list_voices() == []
