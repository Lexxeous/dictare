"""The simulated hotkey is local and exists only for source development."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from dictare.core.http_server import OpenVIPServer


def test_development_hotkey_is_local_and_same_origin(monkeypatch):
    monkeypatch.setenv("DICTARE_DEV_MODE", "1")
    controller = MagicMock()
    server = OpenVIPServer(MagicMock(), controller)
    client = TestClient(server._app, base_url="http://127.0.0.1:18770", client=("127.0.0.1", 1234))
    assert client.post("/api/dev/hotkey", headers={"Origin": "http://127.0.0.1:18770"}).json() == {"status": "ok"}
    controller.on_hotkey_tap.assert_called_once()
    assert client.post("/api/dev/hotkey", headers={"Origin": "https://attacker.example"}).status_code == 403
    assert controller.on_hotkey_tap.call_count == 1


def test_development_hotkey_is_not_registered_in_normal_runtime(monkeypatch):
    monkeypatch.delenv("DICTARE_DEV_MODE", raising=False)
    server = OpenVIPServer(MagicMock(), MagicMock())
    client = TestClient(server._app)
    assert client.post("/api/dev/hotkey").status_code == 404
