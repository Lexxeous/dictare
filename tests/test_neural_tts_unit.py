"""Test local synthesis backends with subprocess and downloads isolated."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.tts import outetts, piper


def test_outetts_availability_is_cached(monkeypatch):
    apple = Mock(return_value=True)
    available = Mock(return_value=True)
    monkeypatch.setattr(outetts, 'is_apple_silicon', apple)
    monkeypatch.setattr(outetts, '_has_mlx_audio', available)
    engine = outetts.OuteTTS(model_size='unknown')
    assert engine.is_available() and engine.is_available()
    assert engine._model_repo == outetts.OUTETTS_MODELS['small'][0]
    apple.assert_called_once()
    available.assert_called_once()


def test_outetts_speak_uses_cache_or_generates(monkeypatch):
    engine = outetts.OuteTTS()
    monkeypatch.setattr(engine, 'is_available', lambda: True)
    monkeypatch.setattr(engine, '_ensure_models_downloaded', lambda: True)
    play = Mock()
    monkeypatch.setattr(outetts, 'play_audio_native', play)
    monkeypatch.setattr(outetts, 'cache_hit', lambda key: Path('/cached.wav'))
    assert engine.speak('hello', volume=0.5)
    assert play.call_args.kwargs['volume'] == 0.5
    monkeypatch.setattr(outetts, 'cache_hit', lambda key: None)
    generate = Mock(return_value=True)
    monkeypatch.setattr(engine, '_generate_and_cache', generate)
    assert engine.speak('hello')
    assert generate.call_args.args[0] == 'hello'


@pytest.mark.parametrize('outcome', ['success', 'failed', 'missing'])
def test_outetts_generate_handles_subprocess_results(monkeypatch, outcome):
    engine = outetts.OuteTTS()
    def run(cmd, **kwargs):
        if outcome == 'success':
            Path(cmd[cmd.index('--file_prefix') + 1] + '_000.wav').write_bytes(b'wave')
        return SimpleNamespace(returncode=int(outcome == 'failed'), stderr=b'error')
    monkeypatch.setattr(outetts.subprocess, 'run', run)
    save = Mock(return_value=Path('/cached.wav'))
    play = Mock()
    evict = Mock()
    monkeypatch.setattr(outetts, 'cache_save', save)
    monkeypatch.setattr(outetts, 'play_audio_native', play)
    monkeypatch.setattr(outetts, 'cache_evict', evict)
    assert engine._generate_and_cache('hello', 'key') is (outcome == 'success')
    assert play.called is (outcome == 'success')
    assert evict.called is (outcome == 'success')


def test_piper_falls_back_to_default_voice(monkeypatch):
    monkeypatch.setattr(piper.PiperTTS, '_detect_piper', lambda self: 'piper')
    engine = piper.PiperTTS(language='en', voice='missing')
    download = Mock(side_effect=[None, Path('/default.onnx')])
    monkeypatch.setattr(engine, '_download_voice', download)
    assert engine._get_model_path() == Path('/default.onnx')
    assert engine.voice == 'en_US-lessac-medium'
    download.side_effect = [None]
    with pytest.raises(RuntimeError):
        engine._get_model_path()


def test_piper_downloads_both_files_and_removes_failed_download(monkeypatch, tmp_path):
    import urllib.request
    monkeypatch.setattr(piper, '_VOICES_DIR', tmp_path)
    fetch = Mock(side_effect=lambda url, dest: dest.write_bytes(b'data'))
    monkeypatch.setattr(urllib.request, 'urlretrieve', fetch)
    path = piper.PiperTTS._download_voice('en_US-lessac-medium')
    assert path.exists()
    assert fetch.call_count == 2
    assert '/en/en_US/lessac/medium/' in fetch.call_args.args[0]
    assert piper.PiperTTS._download_voice('en_US-lessac-medium') == path
    assert fetch.call_count == 2
    fetch.side_effect = OSError('offline')
    assert piper.PiperTTS._download_voice('fr_FR-test-low') is None


@pytest.mark.parametrize('returncode', [0, 1])
def test_piper_synthesis_cleans_temporary_audio(monkeypatch, returncode):
    monkeypatch.setattr(piper.PiperTTS, '_detect_piper', lambda self: 'piper')
    engine = piper.PiperTTS()
    monkeypatch.setattr(engine, '_get_model_path', lambda: Path('/model.onnx'))
    monkeypatch.setattr(piper, 'cache_hit', lambda key: None)
    run = Mock(return_value=SimpleNamespace(returncode=returncode, stderr=b'failed'))
    monkeypatch.setattr(piper.subprocess, 'run', run)
    monkeypatch.setattr(piper, 'cache_save', lambda key, path: Path('/cached.wav'))
    play = Mock()
    monkeypatch.setattr(piper, 'play_audio_native', play)
    monkeypatch.setattr(piper, 'cache_evict', Mock())
    assert engine.speak('hello') is (returncode == 0)
    output = Path(run.call_args.args[0][-1])
    assert not output.exists()
    assert play.called is (returncode == 0)
