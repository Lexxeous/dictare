"""Status streams publish immediately and release their registrations."""
import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI

from dictare.core import http_routes_openvip as routes


def test_stream_sends_initial_status_and_cleans_up(monkeypatch):
    server = SimpleNamespace(status_queues=[], status_queues_lock=threading.Lock(),
                             engine=SimpleNamespace(get_status=lambda: {"state": "ready"}))
    app = FastAPI()
    routes.register_openvip_routes(app, server)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/openvip/status/stream")
    monkeypatch.setattr(routes, "EventSourceResponse", lambda generator: generator)

    async def run():
        request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=[False, True]))
        stream = await endpoint(request)
        assert len(server.status_queues) == 1
        event = await anext(stream)
        assert json.loads(event["data"]) == {"state": "ready"}
        assert [event async for event in stream] == []
        assert server.status_queues == []

    asyncio.run(run())


def test_stream_evicts_oldest_connection(monkeypatch):
    server = SimpleNamespace(status_queues=[asyncio.Queue() for _ in range(routes._MAX_STATUS_STREAMS)],
                             status_queues_lock=threading.Lock(),
                             engine=SimpleNamespace(get_status=lambda: {"state": "ready"}))
    oldest = server.status_queues[0]
    app = FastAPI()
    routes.register_openvip_routes(app, server)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/openvip/status/stream")
    monkeypatch.setattr(routes, "EventSourceResponse", lambda generator: generator)

    async def run():
        stream = await endpoint(SimpleNamespace(is_disconnected=AsyncMock(return_value=False)))
        assert await oldest.get() is None
        assert oldest not in server.status_queues
        assert len(server.status_queues) == routes._MAX_STATUS_STREAMS
        await anext(stream)
        await stream.aclose()
        assert len(server.status_queues) == routes._MAX_STATUS_STREAMS - 1

    asyncio.run(run())
