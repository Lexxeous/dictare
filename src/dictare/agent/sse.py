"""SSE Agent - delivers OpenVIP messages via the HTTP server's SSE queue."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from dictare.agent.base import BaseAgent, OpenVIPMessage

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer

class SSEAgent(BaseAgent):
    """Agent that delivers messages via the HTTP server's SSE queue.

    When an SSE client connects to GET /agents/{agent_id}/messages,
    the server creates an asyncio.Queue for that agent. This agent
    implementation puts messages into that queue via the server's
    thread-safe put_message() method.
    """

    def __init__(
        self, agent_id: str, server: OpenVIPServer, *, queue: asyncio.Queue | None = None,
    ) -> None:
        super().__init__(agent_id)
        self._server = server
        self._connection_queue = queue

    def bind_for_review(self) -> BoundSSEAgent:
        """Freeze the connection identity for a deferred message."""
        return BoundSSEAgent(self)

    def send(self, message: OpenVIPMessage) -> bool:
        """Send message via the server's SSE queue.

        Args:
            message: OpenVIP message dict.

        Returns:
            True if message was queued, False if agent not connected.
        """
        return self._server.put_message(self._id, message)


class BoundSSEAgent(BaseAgent):
    """Delivery restricted to one SSE connection, for deferred review.

    Success means the message was scheduled on the original queue, not that
    the remote process has acknowledged or processed it.
    """

    def __init__(self, agent: SSEAgent) -> None:
        super().__init__(agent.id)
        self._server = agent._server
        self._queue = agent._connection_queue

    def send(self, message: OpenVIPMessage) -> bool:
        if self._queue is None:
            return False
        return self._server.put_message_for_queue(self.id, message, self._queue)
