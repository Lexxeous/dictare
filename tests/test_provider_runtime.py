import asyncio

from dictare.agent.provider_routing import ProviderSession
from dictare.agent.provider_runtime import ProviderRuntime


class FakeProvider:
    id = "codex"

    def __init__(self):
        self.target = ProviderSession("codex", "one", "/work", "One", "connection")
        self.sent = []
        self.closed = False

    async def sessions(self):
        return [self.target]

    async def send(self, session, prompt):
        self.sent.append((session, prompt))

    async def close(self):
        self.closed = True


def test_runtime_delivers_from_an_existing_event_loop():
    provider = FakeProvider()
    runtime = ProviderRuntime(provider)

    async def run():
        assert runtime.deliver(provider.target, "hello")
        assert (await asyncio.wrap_future(runtime.submit(runtime.router.snapshot()))).selected == ("codex", "one")

    try:
        asyncio.run(run())
        assert provider.sent == [(provider.target, "hello")]
    finally:
        runtime.close()
    assert provider.closed
