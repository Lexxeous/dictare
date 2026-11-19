"""Tests for VAD model discovery and lazy session initialization."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.audio import vad


def test_model_discovery_checks_package_and_model_file(monkeypatch, tmp_path):
    monkeypatch.setattr(vad.importlib.util, "find_spec", lambda _: None)
    with pytest.raises(RuntimeError, match="not installed"):
        vad._find_silero_model_path()

    monkeypatch.setattr(vad.importlib.util, "find_spec", lambda _: SimpleNamespace(submodule_search_locations=[str(tmp_path)]))
    with pytest.raises(FileNotFoundError, match="silero_vad_v6.onnx"):
        vad._find_silero_model_path()
    model = tmp_path / "assets" / "silero_vad_v6.onnx"
    model.parent.mkdir()
    model.touch()
    assert vad._find_silero_model_path() == str(model)


def test_session_uses_cpu_and_bounded_threads(monkeypatch):
    import onnxruntime

    options = SimpleNamespace()
    create = Mock(return_value="session")
    monkeypatch.setattr(vad, "_find_silero_model_path", lambda: "model.onnx")
    monkeypatch.setattr(onnxruntime, "SessionOptions", lambda: options)
    monkeypatch.setattr(onnxruntime, "InferenceSession", create)
    assert vad._create_vad_session() == "session"
    create.assert_called_once_with("model.onnx", providers=["CPUExecutionProvider"], sess_options=options)
    assert (options.inter_op_num_threads, options.intra_op_num_threads) == (1, 1)
    assert options.enable_cpu_mem_arena is False
    assert options.log_severity_level == 4


@pytest.mark.parametrize("indicator,headless", [(False, False), (True, False), (False, True)])
def test_model_load_is_lazy_and_resets_state(monkeypatch, indicator, headless):
    from dictare.utils import loading

    session = object()
    create = Mock(return_value=session)
    indicator_call = Mock(side_effect=lambda _key, _name, load, **kwargs: load())
    monkeypatch.setattr(vad, "_create_vad_session", create)
    monkeypatch.setattr(loading, "load_with_indicator", indicator_call)
    engine = vad.SileroVAD()
    engine._load_model(with_indicator=indicator, headless=headless)
    assert engine._model.session is session
    assert engine._context.shape == (1, 64)
    engine._load_model()
    create.assert_called_once()
    assert indicator_call.called is (indicator or headless)
