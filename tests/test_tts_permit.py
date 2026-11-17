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


def test_worker_checks_token_and_fails_closed(monkeypatch):
    import json
    from unittest.mock import patch

    from dictare.tts.worker import _playback_permitted

    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"allowed": True}).encode()
    with patch("urllib.request.urlopen", return_value=response) as send:
        assert _playback_permitted("http://localhost:8770", "secret", "request/id")
        request = send.call_args.args[0]
        assert request.get_header("Authorization") == "Bearer secret"
        assert request.full_url.endswith("/request%2Fid")
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert not _playback_permitted("http://localhost:8770", "secret", "id")


def test_manager_revokes_worker_requests_before_stop_and_resume():
    from dictare.config import Config
    from dictare.core.tts_manager import TTSManager

    manager = TTSManager(Config())
    order = []
    proxy = MagicMock()
    proxy.suspend_requests.side_effect = lambda: order.append("revoke")
    manager._tts_proxy = proxy
    manager.stop_speaking = lambda: order.append("stop") or True
    manager.suspend_for_strict()
    assert order == ["revoke", "stop"]
    assert manager.handle_speech({"text": "ignored"})["status"] == "error"
    manager.resume_after_strict()
    proxy.resume_requests.assert_called_once()
    assert not manager._strict_suspended
