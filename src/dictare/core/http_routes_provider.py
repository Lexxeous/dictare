"""Local control of explicitly managed provider sessions."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from dictare.agent.managed_session import ManagedSessionAgent
from dictare.agent.provider_runtime import ProviderRuntime
from dictare.core.http_routes_review import _require_local_request

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer


class StartSession(BaseModel):
    cwd: str = Field(min_length=1, max_length=4096)
    resume_id: str | None = Field(default=None, max_length=256)


class ProviderSessions:
    """Own managed agents for the lifetime of the local HTTP server."""

    def __init__(self, server: OpenVIPServer) -> None:
        self.server = server
        self.runtime: ProviderRuntime | None = None
        self.agents: dict[str, ManagedSessionAgent] = {}
        self.lock = asyncio.Lock()

    async def call(self, coroutine):
        assert self.runtime is not None
        return await asyncio.wrap_future(self.runtime.submit(coroutine))

    async def start(self, cwd: str, resume_id: str | None) -> None:
        path = Path(cwd).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise HTTPException(400, "Choose an existing absolute working folder")
        async with self.lock:
            if self.runtime is None:
                self.runtime = ProviderRuntime()
            try:
                session = await self.call(self.runtime.codex.start(str(path.resolve()), resume_id=resume_id or None))
            except Exception:
                raise HTTPException(503, "Could not start Codex. Check the SDK installation, login and session ID.") from None
            agent = ManagedSessionAgent(session, self.runtime.deliver)
            if not self.server.engine.register_agent(agent):
                await self.call(self.runtime.codex.stop(session))
                raise HTTPException(409, "Session is already registered")
            self.agents[session.connection_id] = agent

    async def list_sessions(self) -> dict:
        async with self.lock:
            if self.runtime is None:
                return {"sessions": [], "failed": False}
            state = await self.call(self.runtime.router.snapshot())
            live = {s.connection_id for s in state.sessions}
            rows = []
            for connection_id, agent in self.agents.items():
                available = connection_id in live
                if not available and agent.id in self.server.engine._agent_mgr.agents:
                    await asyncio.to_thread(agent.close)
                    self.server.engine.unregister_agent(agent.id, fallback=False)
                draft, failed = await asyncio.to_thread(agent.snapshot)
                session = agent.session
                rows.append({"connection_id": connection_id, "agent_id": agent.id,
                             "provider": session.provider, "session_id": session.session_id,
                             "cwd": session.cwd, "name": session.name, "available": available,
                             "selected": self.server.engine._agent_mgr.current_agent == agent.id,
                             "draft": draft, "delivery_failed": failed})
            return {"sessions": rows, "failed": bool(state.failed_providers)}

    async def select(self, connection_id: str) -> None:
        async with self.lock:
            agent = self.agents.get(connection_id)
            if not agent or not self.runtime:
                raise HTTPException(404, "Session not found")
            try:
                state = await self.call(self.runtime.router.select(agent.session.provider, agent.session.session_id))
                if not any(s == agent.session for s in state.sessions):
                    raise ValueError("Connection changed")
            except Exception:
                raise HTTPException(409, "Session is unavailable") from None
            self.server.engine.switch_to_agent_by_name(agent.id)

    async def turns(self, connection_id: str) -> list[dict]:
        async with self.lock:
            agent = self.agents.get(connection_id)
            if not agent or not self.runtime:
                raise HTTPException(404, "Session not found")
            try:
                turns = await self.call(self.runtime.codex.turns(agent.session))
                return [{"id": turn.id, "status": turn.status, "response": turn.response} for turn in turns]
            except Exception:
                raise HTTPException(503, "Could not read session responses") from None

    async def stop(self, connection_id: str) -> None:
        async with self.lock:
            agent = self.agents.pop(connection_id, None)
            if not agent or not self.runtime:
                raise HTTPException(404, "Session not found")
            await asyncio.to_thread(agent.close)
            self.server.engine.unregister_agent(agent.id, fallback=False)
            try:
                await self.call(self.runtime.codex.stop(agent.session))
            except Exception:
                pass  # Already disconnected; local target is still retired.

    def close(self) -> None:
        for agent in self.agents.values():
            agent.close()
            self.server.engine.unregister_agent(agent.id, fallback=False)
        self.agents.clear()
        if self.runtime:
            self.runtime.close()
            self.runtime = None


def register_provider_routes(app: FastAPI, server: OpenVIPServer) -> None:
    sessions = server.provider_sessions

    def response(payload: dict) -> JSONResponse:
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    @app.get("/api/provider-sessions")
    async def list_sessions(request: Request) -> JSONResponse:
        _require_local_request(request)
        return response(await sessions.list_sessions())

    @app.post("/api/provider-sessions")
    async def start_session(request: Request, body: StartSession) -> JSONResponse:
        _require_local_request(request)
        await sessions.start(body.cwd, body.resume_id)
        return response({"status": "started"})

    @app.post("/api/provider-sessions/{connection_id}/select")
    async def select_session(request: Request, connection_id: str) -> JSONResponse:
        _require_local_request(request)
        await sessions.select(connection_id)
        return response({"status": "selected"})

    @app.get("/api/provider-sessions/{connection_id}/turns")
    async def get_turns(request: Request, connection_id: str) -> JSONResponse:
        _require_local_request(request)
        return response({"turns": await sessions.turns(connection_id)})

    @app.delete("/api/provider-sessions/{connection_id}")
    async def stop_session(request: Request, connection_id: str) -> JSONResponse:
        _require_local_request(request)
        await sessions.stop(connection_id)
        return response({"status": "stopped"})
