"""Managed Codex app-server sessions, separate from stored session history.

This adapter is not an attachment to an existing terminal process. Each
instance owns the app-server it starts. Approval requests are declined until
Dictare has a user-facing approval flow.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from dictare.agent.provider_routing import ProviderSession


class CodexSessionError(Exception):
    """A managed Codex connection could not be established or used."""


def _decline_server_request(method: str, _params: dict[str, Any] | None) -> dict[str, Any]:
    if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
        return {"decision": "decline"}
    # Unknown requests include questions requiring user input. Stop the reader
    # instead of silently supplying an answer or accepting an approval.
    raise CodexSessionError("Codex requested unsupported interaction")


def _new_client() -> Any:
    try:
        from openai_codex.client import CodexClient, CodexConfig
    except ImportError:
        raise CodexSessionError("Codex session support is not installed") from None
    return CodexClient(
        CodexConfig(client_name="dictare", client_title="Dictare"),
        approval_handler=_decline_server_request,
    )


@dataclass(slots=True)
class _Connection:
    session: ProviderSession
    client: Any


@dataclass(frozen=True, slots=True)
class CodexTurn:
    id: str
    status: str
    response: str


class CodexSessions:
    """Own independent app-server processes for sessions started by Dictare."""

    id = "codex"

    def __init__(
        self, client_factory: Callable[[], Any] = _new_client, *, timeout: float = 15,
    ) -> None:
        self._client_factory = client_factory
        self._timeout = timeout
        self._connections: dict[str, _Connection] = {}
        self._lock = asyncio.Lock()

    async def start(self, cwd: str, *, resume_id: str | None = None) -> ProviderSession:
        """Start a new thread or explicitly resume history in a new process."""
        if not cwd:
            raise CodexSessionError("Working folder is required")
        async with self._lock:
            client = self._client_factory()
            try:
                await self._start_client(client)
                await self._call(client.initialize)
                options = {"cwd": cwd, "approvalPolicy": "on-request", "sandbox": "workspace-write"}
                if resume_id:
                    response = await self._call(client.thread_resume, resume_id, options)
                else:
                    response = await self._call(client.thread_start, options)
                thread = response.thread
                if not thread.id or not response.cwd:
                    raise ValueError("Invalid session response")
                if resume_id and thread.id != resume_id:
                    raise ValueError("Unexpected resumed session")
                if thread.id in self._connections:
                    raise ValueError("Session is already managed")
                session = ProviderSession(
                    self.id, thread.id, str(response.cwd), thread.name or thread.id, uuid4().hex,
                )
                self._connections[thread.id] = _Connection(session, client)
                return session
            except asyncio.CancelledError:
                await asyncio.to_thread(client.close)
                raise
            except Exception:
                await asyncio.to_thread(client.close)
                raise CodexSessionError("Could not start Codex session") from None

    async def sessions(self) -> list[ProviderSession]:
        async with self._lock:
            result = []
            failed = False
            for session_id, connection in list(self._connections.items()):
                try:
                    response = await self._call(connection.client.thread_read, session_id)
                    status = type(response.thread.status.root).__name__
                    if status not in {"IdleThreadStatus", "ActiveThreadStatus"}:
                        raise ValueError("Session is not loaded")
                    result.append(connection.session)
                except Exception:
                    del self._connections[session_id]
                    await asyncio.to_thread(connection.client.close)
                    failed = True
                except asyncio.CancelledError:
                    del self._connections[session_id]
                    await asyncio.to_thread(connection.client.close)
                    raise
            if failed:
                raise CodexSessionError("Could not verify Codex sessions")
            return result

    async def send(self, session: ProviderSession, prompt: str) -> None:
        async with self._lock:
            connection = self._connections.get(session.session_id)
            if connection is None or connection.session != session:
                raise CodexSessionError("Codex session is unavailable")
            try:
                await self._call(connection.client.turn_start, session.session_id, prompt)
            except (TimeoutError, asyncio.CancelledError):
                # Acceptance is unknown on timeout. Retire the connection so a
                # later retry cannot silently duplicate the submitted prompt.
                del self._connections[session.session_id]
                await asyncio.to_thread(connection.client.close)
                raise
            except Exception:
                raise CodexSessionError("Codex could not start the turn") from None

    async def turns(self, session: ProviderSession) -> list[CodexTurn]:
        """Read responses from the exact managed connection, without tool output."""
        async with self._lock:
            connection = self._connections.get(session.session_id)
            if connection is None or connection.session != session:
                raise CodexSessionError("Codex session is unavailable")
            try:
                response = await self._call(connection.client.thread_read, session.session_id, True)
                return [
                    CodexTurn(
                        turn.id,
                        str(turn.status),
                        "\n".join(
                            item.root.text for item in turn.items
                            if type(item.root).__name__ == "AgentMessageThreadItem"
                        ),
                    )
                    for turn in response.thread.turns
                ]
            except (TimeoutError, asyncio.CancelledError):
                del self._connections[session.session_id]
                await asyncio.to_thread(connection.client.close)
                raise
            except Exception:
                raise CodexSessionError("Could not read Codex responses") from None

    async def stop(self, session: ProviderSession) -> None:
        """Close only the matching connection, even if its ID was reused."""
        async with self._lock:
            connection = self._connections.get(session.session_id)
            if connection is None or connection.session != session:
                raise CodexSessionError("Codex session is unavailable")
            del self._connections[session.session_id]
            await asyncio.to_thread(connection.client.close)

    async def _call(self, function: Callable[..., Any], *args: Any) -> Any:
        return await asyncio.wait_for(asyncio.to_thread(function, *args), timeout=self._timeout)

    async def _start_client(self, client: Any) -> None:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(client.start)
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), timeout=self._timeout)
        except BaseException:
            # This callback survives shutdown of the asyncio loop. Startup can
            # finish after a cancelled HTTP request or server shutdown.
            def close_late(_completed: Any) -> None:
                threading.Thread(target=client.close, daemon=True).start()

            future.add_done_callback(close_late)
            raise
        finally:
            executor.shutdown(wait=False)

    async def close(self) -> None:
        async with self._lock:
            connections, self._connections = self._connections, {}
            for connection in connections.values():
                await asyncio.to_thread(connection.client.close)
