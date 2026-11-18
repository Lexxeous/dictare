"""Conservative routing to provider-confirmed, managed sessions.

This boundary is independent of OpenVIP and of provider-owned history. A
provider must only return sessions it can currently accept prompts for.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProviderSession:
    provider: str
    session_id: str
    cwd: str
    name: str
    connection_id: str

    @property
    def key(self) -> tuple[str, str]:
        return self.provider, self.session_id


class SessionProvider(Protocol):
    """Provider-owned live connections, not a list of historical transcripts."""

    @property
    def id(self) -> str: ...

    async def sessions(self) -> list[ProviderSession]: ...

    async def send(self, session: ProviderSession, prompt: str) -> None:
        """Reject delivery if this exact connection has been replaced or closed."""
        ...


class RoutingError(Exception):
    """No safe delivery target is available or delivery failed."""


class SelectionRequiredError(RoutingError):
    """More than one target is available and none has been selected."""


class SessionUnavailableError(RoutingError):
    """The selected session is no longer provider-confirmed."""


@dataclass(frozen=True, slots=True)
class RoutingSnapshot:
    sessions: tuple[ProviderSession, ...]
    selected: tuple[str, str] | None
    failed_providers: tuple[str, ...]


class ProviderRouter:
    """Serialize selection and delivery so a prompt cannot switch destinations."""

    def __init__(self, providers: list[SessionProvider]) -> None:
        self._providers = {provider.id: provider for provider in providers}
        if len(self._providers) != len(providers):
            raise ValueError("Duplicate provider ID")
        self._selected: tuple[str, str] | None = None
        self._connection_id: str | None = None
        self._lock = asyncio.Lock()

    async def _refresh(self) -> RoutingSnapshot:
        sessions: list[ProviderSession] = []
        failures: list[str] = []
        for provider_id, provider in self._providers.items():
            try:
                found = await provider.sessions()
                keys = [session.key for session in found]
                if any(
                    session.provider != provider_id
                    or not session.session_id
                    or not session.cwd
                    or not session.connection_id
                    for session in found
                ) or len(keys) != len(set(keys)):
                    raise ValueError("Invalid provider session list")
                sessions.extend(found)
            except Exception:
                # Do not log provider exceptions: they can contain prompt text.
                failures.append(provider_id)
        available = {session.key: session.connection_id for session in sessions}
        if available.get(self._selected) != self._connection_id:
            self._selected = None
            self._connection_id = None
        # A failed provider may have other targets, so do not auto-select.
        if self._selected is None and len(sessions) == 1 and not failures:
            self._selected = sessions[0].key
            self._connection_id = sessions[0].connection_id
        return RoutingSnapshot(tuple(sessions), self._selected, tuple(failures))

    async def snapshot(self) -> RoutingSnapshot:
        async with self._lock:
            return await self._refresh()

    async def select(self, provider_id: str, session_id: str) -> RoutingSnapshot:
        async with self._lock:
            state = await self._refresh()
            key = (provider_id, session_id)
            if key not in {session.key for session in state.sessions}:
                raise SessionUnavailableError("Session is unavailable")
            self._selected = key
            self._connection_id = next(s.connection_id for s in state.sessions if s.key == key)
            return RoutingSnapshot(state.sessions, key, state.failed_providers)

    async def send(self, prompt: str) -> None:
        async with self._lock:
            previous = self._selected
            previous_connection = self._connection_id
            state = await self._refresh()
            if previous is not None and (
                previous != state.selected or previous_connection != self._connection_id
            ):
                # Never deliver an already-started prompt to a fallback target.
                raise SessionUnavailableError("Selected session is unavailable")
            if state.selected is None:
                if len(state.sessions) > 1 or state.failed_providers:
                    raise SelectionRequiredError("Choose a session before sending")
                raise SessionUnavailableError("No session is available")
            session = next(session for session in state.sessions if session.key == state.selected)
            await self._send_to(session, prompt)

    async def send_to(self, target: ProviderSession, prompt: str) -> None:
        """Deliver to a previously captured target, never to a new selection.

        Providers must also reject a connection replaced between refresh and send.
        """
        async with self._lock:
            state = await self._refresh()
            if not any(
                session.key == target.key and session.connection_id == target.connection_id
                for session in state.sessions
            ):
                raise SessionUnavailableError("Selected session is unavailable")
            await self._send_to(target, prompt)

    async def _send_to(self, target: ProviderSession, prompt: str) -> None:
        try:
            await self._providers[target.provider].send(target, prompt)
        except Exception:
            # Provider exceptions may include the prompt, including in tracebacks.
            raise RoutingError("Provider could not accept the prompt") from None
