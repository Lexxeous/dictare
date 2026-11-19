"""STT selection and loading contracts."""

from unittest.mock import MagicMock

import pytest

from dictare.stt.factory import create_stt_engine


@pytest.mark.parametrize("model,accelerated,mlx,expected", [
    ("parakeet-tdt-0.6b-v2", True, True, "parakeet"),
    ("base", True, True, "mlx"),
    ("base", False, True, "faster"),
    ("base", True, False, "faster"),
])
def test_engine_selection_and_options(monkeypatch, model, accelerated, mlx, expected):
    config = MagicMock()
    config.stt.model = "small"
    config.stt.hw_accel = accelerated
    config.stt.advanced.device = "cpu"
    config.stt.advanced.compute_type = "int8"
    config.log_level = "debug"
    engines = {name: MagicMock() for name in ("parakeet", "mlx", "faster")}
    monkeypatch.setattr("dictare.stt.parakeet.ParakeetEngine", lambda: engines["parakeet"])
    monkeypatch.setattr("dictare.stt.mlx_whisper.MLXWhisperEngine", lambda: engines["mlx"])
    monkeypatch.setattr("dictare.stt.faster_whisper.FasterWhisperEngine", lambda: engines["faster"])
    monkeypatch.setattr("dictare.utils.hardware.is_mlx_available", lambda: mlx)
    engine = create_stt_engine(config, model, headless=True)
    assert engine is engines[expected]
    engine.load_model.assert_called_once_with(model, device="cpu", compute_type="int8", console=None, verbose=True, headless=True)


def test_default_model(monkeypatch):
    config = MagicMock()
    config.stt.model = "base"
    config.stt.hw_accel = False
    engine = MagicMock()
    monkeypatch.setattr("dictare.stt.faster_whisper.FasterWhisperEngine", lambda: engine)
    assert create_stt_engine(config) is engine
    assert engine.load_model.call_args.args == ("base",)
