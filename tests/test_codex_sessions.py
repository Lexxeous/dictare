"""Managed sessions use provider confirmations, never history enumeration."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from dictare.agent.codex_sessions import CodexSessionError, CodexSessions, _decline_server_request
from dictare.agent.provider_routing import ProviderRouter, RoutingError


class IdleThreadStatus:
    pass


class AgentMessageThreadItem:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, session_id="one", fail=None):
        self.session_id = session_id
        self.fail = fail
        self.closed = False
        self.started = False
        self.sent = []
        self.resume_args = None

    def start(self):
        self.started = True

    def initialize(self):
        if self.fail == "initialize":
            raise RuntimeError("private")

    def thread_start(self, params):
        return self._response(params)

    def thread_resume(self, session_id, params):
        self.resume_args = session_id
        return self._response(params)

    def _response(self, params):
        return SimpleNamespace(thread=SimpleNamespace(id=self.session_id, name="Example"), cwd=params["cwd"])

    def thread_read(self, session_id, include_turns=False):
        if self.fail == "read":
            raise RuntimeError("private")
        turns = [SimpleNamespace(
            id="turn", status="completed",
            items=[SimpleNamespace(root=AgentMessageThreadItem("Response"))],
        )] if include_turns else []
        return SimpleNamespace(thread=SimpleNamespace(
            status=SimpleNamespace(root=IdleThreadStatus()), turns=turns,
        ))

    def turn_start(self, session_id, prompt):
        if self.fail == "send":
            raise RuntimeError(prompt)
        self.sent.append((session_id, prompt))

    def close(self):
        self.closed = True


def test_managed_start_resume_and_delivery():
    async def run():
        clients = [FakeClient("one"), FakeClient("two")]
        provider = CodexSessions(lambda: clients.pop(0))
        first = await provider.start("/work")
        second = await provider.start("/work", resume_id="two")
        assert [s.session_id for s in await provider.sessions()] == ["one", "two"]
        router = ProviderRouter([provider])
        await router.select("codex", first.session_id)
        await router.send("hello")
        assert provider._connections["one"].client.sent == [("one", "hello")]
        assert provider._connections["two"].client.resume_args == "two"
        assert (await provider.turns(first))[0].response == "Response"
        await provider.stop(second)
        with pytest.raises(CodexSessionError):
            await provider.turns(second)
        await provider.close()
        assert await provider.sessions() == []
        assert second.connection_id != first.connection_id

    asyncio.run(run())


def test_failures_do_not_create_or_retain_targets():
    async def run():
        bad = FakeClient(fail="initialize")
        provider = CodexSessions(lambda: bad)
        with pytest.raises(CodexSessionError):
            await provider.start("/work")
        assert bad.closed and await provider.sessions() == []
        client = FakeClient()
        provider = CodexSessions(lambda: client)
        session = await provider.start("/work")
        router = ProviderRouter([provider])
        client.fail = "send"
        with pytest.raises(RoutingError):
            await router.send("private")
        client.fail = "read"
        with pytest.raises(CodexSessionError):
            await provider.sessions()
        assert client.closed
        with pytest.raises(CodexSessionError):
            await provider.send(session, "private")

    asyncio.run(run())


def test_approval_and_unknown_interactions_fail_closed():
    assert _decline_server_request("item/commandExecution/requestApproval", {}) == {"decision": "decline"}
    assert _decline_server_request("item/fileChange/requestApproval", {}) == {"decision": "decline"}
    with pytest.raises(CodexSessionError):
        _decline_server_request("item/tool/requestUserInput", {})


def test_timeout_retires_connection_without_retry():
    class BlockingClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.released = threading.Event()
            self.calls = 0

        def turn_start(self, session_id, prompt):
            self.calls += 1
            self.released.wait(2)

        def close(self):
            super().close()
            self.released.set()

    async def run():
        client = BlockingClient()
        provider = CodexSessions(lambda: client, timeout=0.05)
        target = await provider.start("/work")
        with pytest.raises(TimeoutError):
            await provider.send(target, "prompt")
        assert client.closed and client.calls == 1
        with pytest.raises(CodexSessionError):
            await provider.send(target, "prompt")
        assert client.calls == 1

    asyncio.run(run())


def test_cancelled_start_closes_a_late_process():
    class SlowClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.entered = threading.Event()
            self.release = threading.Event()
            self.close_count = 0

        def start(self):
            self.entered.set()
            self.release.wait(2)
            self.started = True

        def close(self):
            self.close_count += 1
            super().close()

    async def run():
        client = SlowClient()
        provider = CodexSessions(lambda: client)
        task = asyncio.create_task(provider.start("/work"))
        assert await asyncio.to_thread(client.entered.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        client.release.set()
        for _ in range(100):
            if client.close_count >= 2:
                break
            await asyncio.sleep(0.01)
        assert client.started and client.close_count >= 2
        assert await provider.sessions() == []

    asyncio.run(run())


def test_discovery_failure_blocks_automatic_selection():
    async def run():
        client = FakeClient()
        provider = CodexSessions(lambda: client)
        await provider.start("/work")
        client.fail = "read"
        state = await ProviderRouter([provider]).snapshot()
        assert state.failed_providers == ("codex",)
        assert state.selected is None
        assert client.closed

    asyncio.run(run())


def test_real_sdk_managed_thread_without_authentication(tmp_path):
    """Exercise app-server initialization and a local thread without sending a turn."""
    client_module = pytest.importorskip("openai_codex.client")

    def factory():
        config = client_module.CodexConfig(cwd=str(tmp_path), env={"CODEX_HOME": str(tmp_path)})
        return client_module.CodexClient(config, approval_handler=_decline_server_request)

    async def run():
        provider = CodexSessions(factory)
        try:
            started = await provider.start(str(tmp_path))
            found = await provider.sessions()
            assert found == [started]
        finally:
            await provider.close()

    asyncio.run(run())
