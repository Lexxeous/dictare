"""Foreground session statistics rendering and persistence."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.app.controller import AppController
from dictare.utils import stats


@pytest.mark.parametrize("lifetime_seconds,first_use", [(20, None), (120, "2024-01-01T00:00:00"), (7200, "invalid")])
def test_session_stats_persist_and_display(monkeypatch, capsys, lifetime_seconds, first_use):
    update = Mock(return_value={"total_time_saved_seconds": lifetime_seconds, "sessions": 1, "first_use": first_use})
    monkeypatch.setattr(stats, "update_stats", update)
    controller = object.__new__(AppController)
    controller._config = SimpleNamespace(stats=SimpleNamespace(typing_wpm=40))
    session = SimpleNamespace(count=2, words=100, chars=500, audio_seconds=10, transcription_seconds=2, injection_seconds=1)
    controller._display_session_stats(session)
    assert update.call_args.kwargs["transcriptions"] == 2
    assert update.call_args.kwargs["time_saved_seconds"] > 0
    assert "Transcriptions" in capsys.readouterr().out


def test_empty_session_does_not_persist(monkeypatch):
    update = Mock()
    monkeypatch.setattr(stats, "update_stats", update)
    controller = object.__new__(AppController)
    controller._display_session_stats(None)
    controller._display_session_stats(SimpleNamespace(count=0))
    update.assert_not_called()
