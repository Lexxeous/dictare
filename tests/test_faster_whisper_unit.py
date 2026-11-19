"""Whisper adapter behavior with model and download services isolated."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from dictare.stt import faster_whisper as whisper


def test_transcription_options_and_repetition_filter():
    engine = whisper.FasterWhisperEngine()
    with pytest.raises(RuntimeError, match='Model not loaded'):
        engine.transcribe(np.zeros(2))
    model = Mock()
    model.transcribe.return_value = (
        [SimpleNamespace(text=' hello hello hello '), SimpleNamespace(text='world ')],
        SimpleNamespace(language='en', language_probability=0.9),
    )
    engine._model = model
    result = engine.transcribe(np.zeros(2, dtype=np.float64), language='en', hotwords='Dictare', max_repetitions=2, task='translate')
    assert result.text == 'hello hello world'
    assert result.language == 'en' and result.language_confidence == 0.9
    audio = model.transcribe.call_args.args[0]
    assert audio.dtype == np.float32
    assert model.transcribe.call_args.kwargs['hotwords'] == 'Dictare'
    assert model.transcribe.call_args.kwargs['task'] == 'translate'
    assert engine.is_loaded()


def test_load_cached_model_and_cuda_fallback(monkeypatch):
    model = Mock(side_effect=[RuntimeError('CUDA error'), object()])
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=model))
    import dictare.cuda_setup
    monkeypatch.setattr(dictare.cuda_setup, 'setup_cuda', lambda **_: (True, 'cuda'))
    monkeypatch.setattr(whisper, '_get_cached_model_path', lambda _: '/cached/model')
    engine = whisper.FasterWhisperEngine()
    engine.load_model('base', device='cuda', compute_type='float16', console=Mock())
    assert model.call_count == 2
    assert model.call_args.kwargs['device'] == 'cpu'
    assert model.call_args.kwargs['compute_type'] == 'int8'
    assert engine.model_size == 'base' and engine._device == 'cpu'


def test_load_uncached_model_and_propagate_non_cuda_error(monkeypatch):
    model = Mock(side_effect=ValueError('broken model'))
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=model))
    monkeypatch.setattr(whisper, '_get_cached_model_path', lambda _: None)
    download = Mock(return_value='/downloaded')
    monkeypatch.setattr(whisper, '_download_model_with_progress', download)
    engine = whisper.FasterWhisperEngine()
    with pytest.raises(ValueError, match='broken model'):
        engine.load_model('tiny')
    download.assert_called_once_with('tiny', None)
    assert not engine.is_loaded()


def test_cached_path_checks(monkeypatch, tmp_path):
    model = tmp_path / 'model.bin'
    model.touch()
    loader = Mock(return_value=str(model))
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(try_to_load_from_cache=loader))
    assert whisper._get_cached_model_path('base') == str(tmp_path)
    assert whisper._is_model_cached('base')
    assert whisper._is_turbo_model_cached()
    loader.side_effect = OSError('unavailable')
    assert whisper._get_cached_model_path('base') is None
    assert whisper._get_turbo_model_path() is None
