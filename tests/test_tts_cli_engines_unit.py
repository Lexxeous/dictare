"""Exercise CLI-backed speech engines without launching speech or audio."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.tts import coqui, espeak


@pytest.mark.parametrize(('module', 'cls', 'command_attr'), [
    (espeak, espeak.EspeakTTS, '_cmd'),
    (coqui, coqui.CoquiTTS, '_tts_cmd'),
])
def test_missing_binary_and_cache_hit(monkeypatch, tmp_path, module, cls, command_attr):
    monkeypatch.setattr(cls, '_detect_espeak' if module is espeak else '_detect_tts', lambda _: None)
    engine = cls(language='en')
    assert not engine.is_available()
    assert not engine.speak('hello')
    setattr(engine, command_attr, '/fake/tts')
    audio = tmp_path / 'cached.wav'
    monkeypatch.setattr(module, 'cache_hit', lambda _: audio)
    play = Mock()
    monkeypatch.setattr(module, 'play_audio_native', play)
    assert engine.check_cache('hello') == audio
    assert engine.speak('hello', voice='ignored', language='ignored', volume=0.5)
    play.assert_called_once_with(audio, timeout=120.0, volume=0.5)


@pytest.mark.parametrize(('module', 'cls', 'detect'), [
    (espeak, espeak.EspeakTTS, '_detect_espeak'),
    (coqui, coqui.CoquiTTS, '_detect_tts'),
])
def test_generation_and_failed_process(monkeypatch, tmp_path, module, cls, detect):
    monkeypatch.setattr(cls, detect, lambda _: '/fake/tts')
    monkeypatch.setattr(module, 'cache_hit', lambda _: None)
    saved = tmp_path / 'saved.wav'
    save = Mock(return_value=saved)
    play = Mock()
    evict = Mock()
    run = Mock(return_value=SimpleNamespace(returncode=0, stderr=b''))
    monkeypatch.setattr(module, 'cache_save', save)
    monkeypatch.setattr(module, 'play_audio_native', play)
    monkeypatch.setattr(module, 'cache_evict', evict)
    monkeypatch.setattr(module.subprocess, 'run', run)
    engine = cls(language='en')
    assert engine.speak('hello')
    source = save.call_args.args[1]
    assert not source.exists()
    play.assert_called_once_with(saved, timeout=120.0, volume=1.0)
    evict.assert_called_once()
    assert 'hello' in run.call_args.args[0]
    run.return_value = SimpleNamespace(returncode=1, stderr=b'bad')
    assert not engine.speak('error')
    run.side_effect = OSError('failed')
    assert not engine.speak('error')


def test_espeak_generation_without_playback(monkeypatch):
    monkeypatch.setattr(espeak.EspeakTTS, '_detect_espeak', lambda _: '/fake/espeak')
    monkeypatch.setattr(espeak, 'cache_hit', lambda _: None)
    monkeypatch.setattr(espeak, 'cache_save', lambda _key, path: path)
    monkeypatch.setattr(espeak, 'cache_evict', Mock())
    play = Mock()
    monkeypatch.setattr(espeak, 'play_audio_native', play)
    monkeypatch.setattr(espeak.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    engine = espeak.EspeakTTS(language='it', speed=150)
    assert engine.speak('ciao', play=False)
    play.assert_not_called()
    assert engine.get_name() == '/fake/espeak'


def test_coqui_voice_and_language_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(coqui.CoquiTTS, '_detect_tts', lambda _: '/fake/tts')
    monkeypatch.setattr(coqui, 'cache_hit', lambda _: None)
    monkeypatch.setattr(coqui, 'cache_save', lambda _key, path: path)
    monkeypatch.setattr(coqui, 'cache_evict', Mock())
    monkeypatch.setattr(coqui, 'play_audio_native', Mock())
    run = Mock(return_value=SimpleNamespace(returncode=0, stderr=b''))
    monkeypatch.setattr(coqui.subprocess, 'run', run)
    voice = tmp_path / 'voice.wav'
    voice.touch()
    engine = coqui.CoquiTTS(language='invalid', voice=str(voice))
    assert engine.language == 'en'
    assert engine.speak('hello')
    args = run.call_args.args[0]
    assert args[args.index('--speaker_wav') + 1] == str(voice)
    assert run.call_args.kwargs['env']['COQUI_TOS_AGREED'] == '1'
    assert engine.get_name() == 'coqui'
