"""Engine initialization orchestration without loading models or devices."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.core.engine import DictareEngine


@pytest.fixture
def setup_engine(monkeypatch):
    from dictare.core import engine as module

    engine = object.__new__(DictareEngine)
    engine.config = SimpleNamespace(
        stt=SimpleNamespace(model="tiny", hw_accel=False),
        audio=SimpleNamespace(output_device="speaker"),
        tts=SimpleNamespace(engine="espeak"),
        pipeline=SimpleNamespace(mute_filter=SimpleNamespace(listen_phrases=["resume"])),
        hotkey=SimpleNamespace(), log_level="debug",
    )
    engine.tts_mgr = Mock()
    engine.tts_mgr.loading_status = {"name": "tts", "status": "done"}
    engine._hotkey_enabled = True
    engine._on_audio_control_poisoned = Mock()
    engine._on_vad_speech_start = Mock()
    engine._on_vad_speech_end = Mock()
    engine._on_max_speech_duration = Mock()
    engine._notify_status = Mock()
    stt = Mock()
    audio = Mock()
    hotkey = Mock()
    save = Mock()
    output = Mock()
    monkeypatch.setattr(module, "create_stt_engine", stt)
    monkeypatch.setattr(module, "AudioManager", audio)
    monkeypatch.setattr(module, "create_hotkey_listener", hotkey)
    monkeypatch.setattr("dictare.utils.stats.get_model_load_time", lambda _: None)
    monkeypatch.setattr("dictare.utils.stats.save_model_load_time", save)
    monkeypatch.setattr("dictare.audio.beep.set_output_device", output)
    return engine, stt, audio, hotkey, save, output


def test_initializes_models_audio_tts_hotkey_and_output(setup_engine):
    engine, stt, audio, hotkey, save, output = setup_engine
    engine.init_components(headless=True, http_server="server")
    stt.assert_called_once_with(engine.config, headless=True)
    audio.return_value.initialize.assert_called_once()
    assert audio.return_value.initialize.call_args.kwargs["headless"] is True
    assert audio.return_value.on_devices_updated is engine._notify_status
    engine.tts_mgr.load.assert_called_once_with(http_server="server", estimated=1)
    engine.tts_mgr.precache_phrases.assert_called_once_with(["resume"])
    hotkey.assert_called_once_with(engine.config.hotkey)
    output.assert_called_once_with("speaker")
    assert [item["status"] for item in engine._loading_models] == ["done"] * 3
    assert save.call_count == 2


def test_hotkey_failure_is_nonfatal(setup_engine):
    engine, _, _, hotkey, _, _ = setup_engine
    hotkey.side_effect = RuntimeError("unavailable")
    engine.init_components()
    assert engine._hotkey is None


@pytest.mark.parametrize("failed_component", ["stt", "vad"])
def test_model_initialization_errors_propagate(setup_engine, failed_component):
    engine, stt, audio, _, _, _ = setup_engine
    target = stt if failed_component == "stt" else audio.return_value.initialize
    target.side_effect = ValueError("broken model")
    with pytest.raises(ValueError, match="broken model"):
        engine.init_components()
    engine.tts_mgr.load.assert_not_called()
