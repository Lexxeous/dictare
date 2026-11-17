"""The chosen resume identity must survive the terminal's initial clear."""

import io
from unittest.mock import MagicMock

import pytest

from dictare.agent import mux


def test_resume_message_is_printed_after_clear_before_child_start(tmp_path, monkeypatch):
    output = io.BytesIO()
    terminal = io.TextIOWrapper(output, encoding="utf-8", newline="")
    client = MagicMock()
    client.get_status.return_value.connected_agents = []
    monkeypatch.setattr("openvip.Client", lambda *args, **kwargs: client)
    monkeypatch.setattr(mux.sys, "stdout", terminal)
    monkeypatch.setattr(mux, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mux, "setup_logging", lambda **kwargs: None)
    monkeypatch.setattr(mux, "_report_focus", lambda *args: None)
    monkeypatch.setattr(mux, "_print_session_summary", lambda *args: None)

    session = MagicMock()

    def start():
        terminal.flush()
        assert output.getvalue() == (
            b"\x1b[2J\x1b[H[dictare] Resuming codex session example-id\r\n"
        )
        raise FileNotFoundError("intentional fake child failure")

    session.start.side_effect = start
    monkeypatch.setattr(mux, "PTYSession", lambda *args, **kwargs: session)
    with pytest.raises(FileNotFoundError, match="intentional fake"):
        mux.run_agent(
            "example", ["codex"], startup_message="Resuming codex session example-id"
        )
    session.cleanup.assert_called_once()
