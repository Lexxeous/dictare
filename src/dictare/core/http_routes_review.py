"""Loopback-only, same-origin access to the in-memory prompt review slot."""

from __future__ import annotations

import asyncio
import ipaddress
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer


def _require_local_request(request: Request) -> None:
    """Reject remote, DNS-rebinding and cross-origin access to draft content."""
    try:
        local_peer = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local_peer = False
    host = request.url.hostname
    if not local_peer or host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="Review is available only locally")
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            raise HTTPException(status_code=403, detail="Cross-origin review access denied") from None
        if parsed.scheme != request.url.scheme or parsed.netloc != request.url.netloc or parsed.path:
            raise HTTPException(status_code=403, detail="Cross-origin review access denied")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-origin review access denied")


def register_review_routes(app: FastAPI, server: OpenVIPServer) -> None:
    """Read and resolve the current draft without exposing other messages."""

    @app.get("/api/review")
    async def get_review(request: Request) -> JSONResponse:
        _require_local_request(request)
        draft = server.engine.review_snapshot()
        payload = None if draft is None else {
            "id": draft.id,
            "destination": draft.destination,
            "messages": [str(message.get("text", "")) for message in draft.messages],
            "sending": draft.sending,
            "can_send": draft.can_send,
        }
        return JSONResponse({"draft": payload}, headers={"Cache-Control": "no-store"})

    @app.post("/api/review/{draft_id}/{action}")
    async def resolve_review(draft_id: str, action: str, request: Request) -> JSONResponse:
        _require_local_request(request)
        if action == "send":
            result = await asyncio.to_thread(server.engine.send_review, draft_id)
        elif action == "discard":
            result = "discarded" if server.engine.discard_review(draft_id) else "unavailable"
        else:
            raise HTTPException(status_code=404, detail="Unknown review action")
        return JSONResponse({"status": result}, headers={"Cache-Control": "no-store"})
