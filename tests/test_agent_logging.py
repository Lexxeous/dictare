"""Tests for agent logging and explicit transcript-content opt-in."""

from __future__ import annotations

import json
import queue
import threading
from unittest.mock import patch

import pytest
from openvip.models import Transcription

from dictare.agent.mux import _read_from_sse, _write_to_pty, run_agent


def _make_status(agents: list[str]):
    """Create a mock status object with connected_agents."""
    from unittest.mock import MagicMock

    status = MagicMock()
    status.connected_agents = agents
    return status

class TestAgentBannerLogged:
    """Banner info (agent, server, session, command) goes to log file, not stderr."""

    def test_no_banner_on_stderr(self, capsys) -> None:
        """run_agent must NOT print banner lines to stderr."""
        with patch("openvip.Client") as mock_client:
            mock_client.return_value.get_status.side_effect = ConnectionRefusedError
            run_agent("voice", ["echo", "hi"])
        captured = capsys.readouterr()
        # The error message about unreachable engine is OK — we check that
        # the old banner lines (Agent:, Server:, Session:, Running:) are gone.
        assert "Agent: voice" not in captured.err
        assert "Server: http" not in captured.err
        assert "Session:" not in captured.err
        assert "Running:" not in captured.err

    def test_banner_logged_to_agent_file(self, tmp_path, monkeypatch) -> None:
        """Banner info is written to the agent log file."""
        import logging

        monkeypatch.setattr("dictare.agent.mux.SESSIONS_DIR", tmp_path / "sessions")
        log_file = tmp_path / "agent.test.jsonl"
        from dictare.logging.setup import DictareJsonFormatter

        handler = logging.FileHandler(log_file)
        handler.setFormatter(DictareJsonFormatter(source="agent.test"))

        dictare_logger = logging.getLogger("dictare")

        def fake_setup_logging(**kwargs):
            dictare_logger.setLevel(logging.DEBUG)
            dictare_logger.addHandler(handler)
            return handler

        with patch("openvip.Client") as mock_client, \
             patch("dictare.agent.mux.setup_logging", side_effect=fake_setup_logging):
            mock_client.return_value.get_status.return_value = _make_status([])
            # Command will fail at PTY spawn — that's fine, the log happens before
            try:
                run_agent("test", ["__nonexistent__"], clear_on_start=False)
            except (FileNotFoundError, OSError):
                pass
            finally:
                handler.flush()
                handler.close()
                dictare_logger.removeHandler(handler)

        content = log_file.read_text().strip()
        assert content, "Log file should not be empty"
        lines = content.splitlines()
        events = [json.loads(line) for line in lines]
        agent_start = [e for e in events if e.get("event") == "agent_start"]
        assert len(agent_start) == 1
        assert agent_start[0]["agent_id"] == "test"
        assert "server" in agent_start[0]
        assert "command" in agent_start[0]

@pytest.mark.parametrize("verbose", [False, True])
@pytest.mark.parametrize("text", ["private sentence", "Confidential words beyond the old twenty character preview", "Privé 日本語"])
def test_session_content_requires_verbose_without_changing_delivery(tmp_path, text, verbose):
    """Exercise actual SDK receive, PTY delivery and every associated disk event."""
    path = tmp_path / "session.jsonl"
    trigger = "private spoken command"
    message = Transcription.from_dict({
        "openvip": "1.0", "type": "transcription",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2026-01-01T00:00:00Z", "text": text,
        "x_input": {"ops": ["submit"], "trigger": trigger},
    })
    pending: queue.Queue = queue.Queue()
    with patch("openvip.Client") as client:
        client.return_value.subscribe.return_value = [message]
        _read_from_sse("test", "http://127.0.0.1:9999", pending, threading.Event(), path, verbose=verbose)

    writes = []
    pending.put(("error", "test completed"))
    with patch("os.write", side_effect=lambda fd, data: writes.append(data) or len(data)), patch("termios.tcdrain"):
        _write_to_pty(99, pending, threading.Event(), path, verbose=verbose)
    assert writes == [text.encode(), b"\r"]

    entries = [json.loads(line) for line in path.read_text().splitlines()]
    read = next(entry for entry in entries if entry["event"] == "msg_read")
    sent = next(entry for entry in entries if entry["event"] == "msg_sent")
    assert read["chars"] == sent["chars"] == len(text)
    assert sent["submit"] is True
    assert sent["text_bytes"] == len(text.encode())
    if verbose:
        assert read["text"] == sent["text"] == text
        assert sent["submit_trigger"] == trigger
    else:
        assert all("text" not in entry and "submit_trigger" not in entry for entry in entries)
        assert text not in path.read_text()
        assert trigger not in path.read_text()

class TestRunAgentNoQuietParam:
    """Verify --quiet parameter has been removed from run_agent."""

    def test_quiet_param_rejected(self) -> None:
        """run_agent must not accept 'quiet' keyword argument."""
        with patch("openvip.Client") as mock_client:
            mock_client.return_value.get_status.side_effect = ConnectionRefusedError
            try:
                run_agent("test", ["echo"], quiet=True)  # type: ignore[call-arg]
                assert False, "Should have raised TypeError"
            except TypeError as e:
                assert "quiet" in str(e)
