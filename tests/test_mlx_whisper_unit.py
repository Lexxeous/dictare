"""MLX Whisper behavior without a model download or Apple hardware."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from dictare.stt.mlx_whisper import MLXWhisperEngine


@pytest.mark.parametrize("cached", [True, False])
def test_load_uses_cache_or_download(monkeypatch, cached):
    engine = MLXWhisperEngine()
    monkeypatch.setattr(engine, "_is_model_cached", lambda _: cached)
    loader = Mock()
    downloader = Mock()
    monkeypatch.setattr("dictare.utils.loading.load_with_indicator", loader)
    monkeypatch.setattr("dictare.utils.hf_download.download_with_progress", downloader)
    engine.load_model("tiny", headless=True)
    assert engine.is_loaded()
    assert engine.model_size == "tiny"
    if cached:
        assert loader.call_args.args[:2] == ("mlx-community/whisper-tiny-mlx", "STT model")
        assert loader.call_args.kwargs["headless"] is True
        downloader.assert_not_called()
    else:
        assert downloader.call_args.args[0] == "mlx-community/whisper-tiny-mlx"
        assert downloader.call_args.kwargs["fallback_size_gb"] == 3.0
        loader.assert_not_called()


@pytest.mark.parametrize("result, expected", [("/cached/config", True), (None, False)])
def test_cache_check(monkeypatch, result, expected):
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", lambda *args: result)
    assert MLXWhisperEngine()._is_model_cached("owner/model") is expected


def test_cache_error_is_a_miss(monkeypatch):
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", Mock(side_effect=OSError("offline")))
    assert not MLXWhisperEngine()._is_model_cached("owner/model")


def test_transcribe_requires_model():
    with pytest.raises(RuntimeError, match="Model not loaded"):
        MLXWhisperEngine().transcribe(np.zeros(2))


@pytest.mark.parametrize("language,task,expected", [("auto", "transcribe", None), ("fr", "transcribe", "fr"), ("fr", "translate", None)])
def test_transcribe_converts_audio_and_passes_options(monkeypatch, language, task, expected):
    transcribe = Mock(return_value={"text": "  hello world  ", "language": "fr"})
    monkeypatch.setitem(sys.modules, "mlx_whisper", SimpleNamespace(transcribe=transcribe))
    engine = MLXWhisperEngine()
    engine._model_path = "model"
    result = engine.transcribe(np.ones(2, dtype=np.float64), language=language, task=task)
    assert result.text == "hello world"
    assert result.language == "fr"
    assert transcribe.call_args.args[0].dtype == np.float32
    assert transcribe.call_args.kwargs == {"path_or_hf_repo": "model", "language": expected, "task": task}


def test_load_callback_requests_model_with_float16(monkeypatch):
    engine = MLXWhisperEngine()
    monkeypatch.setattr(engine, "_is_model_cached", lambda _: True)
    monkeypatch.setattr("dictare.utils.loading.load_with_indicator", lambda _path, _kind, callback, **kw: callback())
    model_get = Mock()
    mlx = ModuleType("mlx")
    mlx.__path__ = []
    core = ModuleType("mlx.core")
    core.float16 = "float16"
    whisper = ModuleType("mlx_whisper")
    whisper.__path__ = []
    module = ModuleType("mlx_whisper.transcribe")
    module.ModelHolder = SimpleNamespace(get_model=model_get)
    for name, value in (("mlx", mlx), ("mlx.core", core), ("mlx_whisper", whisper), ("mlx_whisper.transcribe", module)):
        monkeypatch.setitem(sys.modules, name, value)
    engine.load_model("custom")
    model_get.assert_called_once_with("mlx-community/whisper-custom-mlx", "float16")
