"""Local session management preserves routing and protects prompt content."""

from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dictare.agent.provider_routing import ProviderSession
from dictare.agent.provider_runtime import ProviderRuntime
from dictare.core.agent_manager import AgentManager
from dictare.core.http_routes_provider import ProviderSessions, register_provider_routes


class FakeProvider:
    id = "codex"

    def __init__(self):
        self.live = {}
        self.sent = []

    async def start(self, cwd, *, resume_id=None):
        name = resume_id or str(len(self.live) + 1)
        session = ProviderSession("codex", name, cwd, name, "conn" + name)
        self.live[name] = session
        return session

    async def sessions(self):
        return list(self.live.values())

    async def send(self, session, prompt):
        self.sent.append((session, prompt))

    async def turns(self, session):
        return [SimpleNamespace(id="turn", status="completed", response="answer")]

    async def stop(self, session):
        self.live.pop(session.session_id, None)

    async def close(self):
        self.live.clear()


def make_client(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr("dictare.core.http_routes_provider.ProviderRuntime", lambda: ProviderRuntime(provider))
    manager = AgentManager()
    engine = Mock(_agent_mgr=manager)
    engine.register_agent.side_effect = manager.register
    engine.unregister_agent.side_effect = manager.unregister
    engine.switch_to_agent_by_name.side_effect = manager.switch_by_name
    server = Mock(engine=engine)
    server.provider_sessions = ProviderSessions(server)
    app = FastAPI()
    register_provider_routes(app, server)
    client = TestClient(app, base_url="http://127.0.0.1:8770", client=("127.0.0.1", 1234))
    return client, server.provider_sessions, provider, manager


def test_lifecycle_and_disappearance_do_not_retarget(monkeypatch, tmp_path):
    client, sessions, provider, manager = make_client(monkeypatch)
    try:
        assert client.post("/api/provider-sessions", json={"cwd": str(tmp_path)}).status_code == 200
        assert client.post("/api/provider-sessions", json={"cwd": str(tmp_path)}).status_code == 200
        result = client.get("/api/provider-sessions")
        assert result.headers["cache-control"] == "no-store"
        first, second = result.json()["sessions"]
        assert first["selected"] and not second["selected"]
        assert client.post(f"/api/provider-sessions/{second['connection_id']}/select").status_code == 200
        assert manager.current_agent == second["agent_id"]
        assert client.get(f"/api/provider-sessions/{second['connection_id']}/turns").json()["turns"][0]["response"] == "answer"
        provider.live.pop("2")
        rows = client.get("/api/provider-sessions").json()["sessions"]
        assert not rows[1]["available"]
        assert manager.current_agent is None
        assert client.post(f"/api/provider-sessions/{second['connection_id']}/select").status_code == 409
        assert client.delete(f"/api/provider-sessions/{second['connection_id']}").status_code == 200
        assert manager.current_agent is None
    finally:
        sessions.close()


def test_routes_reject_cross_origin_and_invalid_folder(monkeypatch):
    client, sessions, _, _ = make_client(monkeypatch)
    try:
        assert client.get("/api/provider-sessions", headers={"host": "attacker.example"}).status_code == 403
        assert client.post("/api/provider-sessions", headers={"origin": "https://attacker.example"}, json={"cwd": "/tmp"}).status_code == 403
        assert client.post("/api/provider-sessions", json={"cwd": "relative"}).status_code == 400
        assert sessions.runtime is None
    finally:
        sessions.close()
