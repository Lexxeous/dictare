"""Source-only helpers; never registered by an installed engine by default."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request

from dictare.core.http_routes_review import _require_local_request

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer


def register_development_routes(app: FastAPI, server: OpenVIPServer) -> None:
    @app.get("/api/dev/identity")
    async def source_identity(request: Request):
        _require_local_request(request)
        return {"source": True, "checkout": os.environ.get("DICTARE_DEV_CHECKOUT", "")}

    @app.post("/api/dev/control")
    async def source_control(request: Request):
        """Restrict lifecycle actions to the explicitly enabled source API."""
        _require_local_request(request)
        body = await request.json()
        if not isinstance(body, dict) or body.get("command") not in {"stt.start", "stt.stop", "engine.shutdown"}:
            raise HTTPException(status_code=400, detail="Unsupported source command")
        return await asyncio.to_thread(server.engine.handle_protocol_command, body)

    @app.post("/api/dev/hotkey")
    async def simulate_hotkey(request: Request):
        """Simulate a tap without registering a competing global shortcut."""
        _require_local_request(request)
        if server.controller is None:
            raise HTTPException(status_code=503, detail="Source controller is unavailable")
        await asyncio.to_thread(server.controller.on_hotkey_tap)
        return {"status": "ok"}
