"""Worker playback permits expire when pending speech is suspended."""

import threading
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from dictare.core.http_server import OpenVIPServer
from dictare.tts.proxy import WorkerTTSEngine


def test_suspension_revokes_pending_and_wakes_speaker():
    server = MagicMock()
    delivered = threading.Event()
    messages = []
    def send(agent_id, message):
        messages.append(message)
        delivered.set()
        return True
    server.put_message.side_effect = send
    proxy = WorkerTTSEngine(server)
    result = []
    thread = threading.Thread(target=lambda: result.append(proxy.speak("private")))
    thread.start()
    assert delivered.wait(timeout=2)
    message_id = messages[0]["id"]
    assert proxy.playback_permitted(message_id)
    proxy.suspend_requests()
    thread.join(timeout=2)
    assert result == [False]
    assert not proxy.playback_permitted(message_id)
    assert not proxy.speak("blocked")
    proxy.complete(message_id, ok=True)
    proxy.resume_requests()
    assert not proxy.playback_permitted(message_id)


def test_permit_endpoint_requires_worker_token_and_pending_request():
    engine = MagicMock()
    server = OpenVIPServer(engine, auth_tokens={"register_tts": "secret"})
    proxy = WorkerTTSEngine(server)
    engine.tts_mgr._tts_proxy = proxy
    proxy._pending["id"] = (threading.Event(), {"ok": False})
    client = TestClient(server._app)
    assert client.get("/internal/tts/permit/id").status_code == 403
    auth = {"Authorization": "Bearer secret"}
    response = client.get("/internal/tts/permit/id", headers=auth)
    assert response.json() == {"allowed": True}
    assert response.headers["cache-control"] == "no-store"
    proxy.suspend_requests()
    assert client.get("/internal/tts/permit/id", headers=auth).json() == {"allowed": False}
