"""A deferred message must not follow an agent ID to a new SSE session."""

import asyncio
from unittest.mock import Mock

from dictare.agent.sse import SSEAgent
from dictare.core.http_server import OpenVIPServer


def test_review_binding_rejects_reconnected_agent_with_same_name():
    server = OpenVIPServer(Mock())
    first = asyncio.Queue()
    second = asyncio.Queue()
    loop = Mock()
    loop.is_running.return_value = True
    server._loop = loop
    server.agent_queues["codex"] = first
    bound = SSEAgent("codex", server, queue=first).bind_for_review()

    assert bound.send({"text": "first"})
    loop.call_soon_threadsafe.assert_called_once_with(first.put_nowait, {"text": "first"})
    server.agent_queues["codex"] = second
    assert not bound.send({"text": "private"})
    assert loop.call_soon_threadsafe.call_count == 1


def test_review_binding_rejects_unknown_connection_and_stopped_loop():
    server = OpenVIPServer(Mock())
    queue = asyncio.Queue()
    server.agent_queues["codex"] = queue
    assert not SSEAgent("codex", server).bind_for_review().send({"text": "private"})
    assert not SSEAgent("codex", server, queue=queue).bind_for_review().send({"text": "private"})
