"""Source-only helpers; never registered by an installed engine by default."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request

from dictare.core.http_routes_review import _require_local_request

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer


def register_development_routes(app: FastAPI, server: OpenVIPServer) -> None:
    @app.post("/api/dev/hotkey")
    async def simulate_hotkey(request: Request):
        """Simulate a tap without registering a competing global shortcut."""
        _require_local_request(request)
        if server.controller is None:
            raise HTTPException(status_code=503, detail="Source controller is unavailable")
        await asyncio.to_thread(server.controller.on_hotkey_tap)
        return {"status": "ok"}
