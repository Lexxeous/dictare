"""Tests for OuteTTS model download and availability decisions."""

from unittest.mock import Mock

import pytest

from dictare.tts import outetts
from dictare.utils import hf_download


@pytest.mark.parametrize("cached", [True, False])
def test_downloads_only_missing_models_and_reuses_ready_state(monkeypatch, cached):
    import huggingface_hub

    check = Mock(return_value=cached)
    download = Mock()
    progress = Mock(side_effect=lambda _repo, callback, **kwargs: callback())
    monkeypatch.setattr(hf_download, "is_repo_cached", check)
    monkeypatch.setattr(hf_download, "download_with_progress", progress)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    engine = outetts.OuteTTS()
    assert engine._ensure_models_downloaded()
    assert engine._ensure_models_downloaded()
    assert check.call_count == 2
    assert download.call_count == (0 if cached else 2)
    if not cached:
        assert [call.args[0] for call in download.call_args_list] == [engine._model_repo, outetts.SNAC_MODEL[0]]


def test_availability_is_cached_and_requires_apple_silicon(monkeypatch):
    apple = Mock(return_value=False)
    mlx = Mock(return_value=True)
    monkeypatch.setattr(outetts, "is_apple_silicon", apple)
    monkeypatch.setattr(outetts, "_has_mlx_audio", mlx)
    engine = outetts.OuteTTS()
    assert not engine.is_available()
    assert not engine.is_available()
    apple.assert_called_once()
    mlx.assert_not_called()
    apple.return_value = True
    assert outetts.OuteTTS().is_available()
    mlx.assert_called_once()
