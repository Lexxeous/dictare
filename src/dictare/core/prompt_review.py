"""Single in-memory review slot for processed messages.

This module does not start capture or send messages. The engine must pause and
invalidate capture before exposing a draft, and the caller owns transport
outcomes. The slot keeps the original agent object and message operations.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from uuid import uuid4

from dictare.agent.base import Agent


class UnavailableReviewAgent:
    """Retain a draft safely when its original target cannot be bound."""

    def __init__(self, agent_id: str) -> None:
        self.id = agent_id

    def send(self, message: dict[str, Any]) -> bool:
        return False


@dataclass(frozen=True)
class ReviewSnapshot:
    """Displayable copy of a draft; never expose the live delivery object."""

    id: str
    destination: str
    messages: list[dict[str, Any]] = field(repr=False)
    sending: bool = False
    can_send: bool = True


@dataclass(frozen=True)
class ReviewClaim:
    """Exclusive delivery claim tied to a specific draft and original agent."""

    id: str
    token: str = field(repr=False)
    agent: Agent = field(repr=False)
    messages: list[dict[str, Any]] = field(repr=False)


class ReviewSlot:
    """Keep at most one draft and serialize claims, discard, and completion."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._id: str | None = None
        self._agent: Agent | None = None
        self._messages: list[dict[str, Any]] = []
        self._claim: str | None = None

    def hold(self, agent: Agent, messages: list[dict[str, Any]]) -> ReviewSnapshot | None:
        """Retain a new draft only if the slot is empty and messages exist."""
        if not messages:
            return None
        copied_messages = deepcopy(messages)
        with self._lock:
            if self._id is not None:
                return None
            self._id = uuid4().hex
            self._agent = agent
            self._messages = copied_messages
            return self._snapshot()

    def occupied(self) -> bool:
        """Check for a draft without copying its contents."""
        with self._lock:
            return self._id is not None

    def snapshot(self) -> ReviewSnapshot | None:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> ReviewSnapshot | None:
        if self._id is None or self._agent is None:
            return None
        return ReviewSnapshot(
            self._id, self._agent.id, deepcopy(self._messages),
            self._claim is not None, not isinstance(self._agent, UnavailableReviewAgent),
        )

    def claim(self, draft_id: str) -> ReviewClaim | None:
        """Claim a matching draft once; competing operations cannot replace it."""
        with self._lock:
            if draft_id != self._id or self._agent is None or self._claim is not None:
                return None
            self._claim = uuid4().hex
            return ReviewClaim(draft_id, self._claim, self._agent, deepcopy(self._messages))

    def finish(self, claim: ReviewClaim, delivered: int) -> bool:
        """Complete a claim, removing only messages confirmed delivered.

        A zero count retains the whole draft for an explicit retry or discard.
        Callers must handle uncertain transport outcomes separately; a failure
        does not necessarily prove that the destination received nothing.
        """
        with self._lock:
            if claim.id != self._id or claim.token != self._claim:
                return False
            if not 0 <= delivered <= len(self._messages):
                raise ValueError("Invalid delivered message count")
            del self._messages[:delivered]
            self._claim = None
            if not self._messages:
                self._clear()
            return True

    def discard(self, draft_id: str) -> bool:
        """Discard only the matching draft, never one currently being sent."""
        with self._lock:
            if draft_id != self._id or self._claim is not None:
                return False
            self._clear()
            return True

    def _clear(self) -> None:
        self._id = None
        self._agent = None
        self._messages = []
        self._claim = None
