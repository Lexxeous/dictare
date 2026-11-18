"""Bridge Dictare's incremental input messages to a managed provider session."""

from __future__ import annotations

import threading
from collections.abc import Callable

from dictare.agent.base import BaseAgent, OpenVIPMessage
from dictare.agent.provider_routing import ProviderSession


class ManagedSessionAgent(BaseAgent):
    """Accumulate newline operations and submit only to one connection.

    A failed submission is never retried automatically: the provider may have
    accepted it even when its acknowledgement was lost.
    """

    def __init__(
        self, session: ProviderSession, deliver: Callable[[ProviderSession, str], bool],
    ) -> None:
        super().__init__(f"{session.provider}:{session.connection_id}")
        self.session = session
        self._deliver = deliver
        self._lock = threading.Lock()
        self._parts: list[str] = []
        self._closed = False
        self._failed = False

    def bind_for_review(self) -> ManagedSessionAgent:
        return self

    def send(self, message: OpenVIPMessage) -> bool:
        with self._lock:
            if self._closed or self._failed:
                return False
            text = str(message.get("text") or "")
            x_input = message.get("x_input")
            ops = x_input.get("ops", []) if isinstance(x_input, dict) else []
            if text:
                self._parts.append(text)
            if "submit" not in ops:
                return True
            prompt = "\n".join(self._parts)
            if not prompt.strip():
                return True
            try:
                accepted = self._deliver(self.session, prompt)
            except Exception:
                accepted = False
            if not accepted:
                self._failed = True
                return False
            self._parts.clear()
            return True

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def snapshot(self) -> tuple[str, bool]:
        """Return the local draft and whether delivery requires attention."""
        with self._lock:
            return "\n".join(self._parts), self._failed
