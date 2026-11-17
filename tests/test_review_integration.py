"""Review mode from configured capture to local HTTP resolution."""

import asyncio
from unittest.mock import Mock

from fastapi.testclient import TestClient

from dictare.agent.sse import SSEAgent
from dictare.config import Config
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState, TranscriptionCompleted
from dictare.core.http_server import OpenVIPServer


def test_configured_review_keeps_captured_connection_and_requires_explicit_send():
    config = Config()
    assert not config.output.review_before_send
    config.output.review_before_send = True
    engine = DictareEngine(config, hotkey_enabled=False)
    server = OpenVIPServer(engine)
    loop = Mock()
    loop.is_running.return_value = True
    server._loop = loop
    first = asyncio.Queue()
    server.agent_queues["codex"] = first
    agent = SSEAgent("codex", server, queue=first)
    client = TestClient(server._app, base_url="http://127.0.0.1:8770", client=("127.0.0.1", 1234))
    engine._state_manager.transition(AppState.TRANSCRIBING, force=True)
    engine._controller._handle_event(TranscriptionCompleted(
        text="hello assistant", agent=agent, source="stt", capture_generation=engine._capture_generation,
    ))
    assert loop.call_soon_threadsafe.call_count == 0
    engine._controller._handle_event(engine._controller._queue.get_nowait())
    assert engine._state_manager.state == AppState.OFF
    draft = client.get("/api/review").json()["draft"]
    assert draft["messages"] == ["hello assistant"] and draft["destination"] == "codex"
    response = client.post(f'/api/review/{draft["id"]}/send')
    assert response.json()["status"] == "scheduled"
    assert loop.call_soon_threadsafe.call_count == 1
    assert client.get("/api/review").json()["draft"] is None
    assert engine._state_manager.state == AppState.OFF


def test_reconnected_agent_does_not_receive_old_reviewed_prompt():
    config = Config()
    config.output.review_before_send = True
    engine = DictareEngine(config, hotkey_enabled=False)
    server = OpenVIPServer(engine)
    loop = Mock()
    loop.is_running.return_value = True
    server._loop = loop
    old = asyncio.Queue()
    server.agent_queues["codex"] = old
    agent = SSEAgent("codex", server, queue=old)
    engine.inject_text("private", agent=agent)
    draft = engine.review_snapshot()
    assert draft is not None
    server.agent_queues["codex"] = asyncio.Queue()
    assert engine.send_review(draft.id) == "failed"
    assert engine.review_snapshot().messages[0]["text"] == "private"
    loop.call_soon_threadsafe.assert_not_called()
