"""Provider routing never treats stored history as a live destination."""

import asyncio
import traceback

import pytest

from dictare.agent.provider_routing import (
    ProviderRouter,
    ProviderSession,
    RoutingError,
    SelectionRequiredError,
    SessionUnavailableError,
)


class Provider:
    def __init__(self, provider_id, sessions=()):
        self.id = provider_id
        self.available = list(sessions)
        self.sent = []
        self.error = False
        self.send_error = False

    async def sessions(self):
        if self.error:
            raise RuntimeError("private provider detail")
        return self.available.copy()

    async def send(self, target, prompt):
        if self.send_error:
            raise RuntimeError(prompt)
        if target not in self.available:
            raise RuntimeError("connection closed")
        self.sent.append((target.session_id, prompt))


def session(provider, session_id, connection_id="connection"):
    return ProviderSession(provider, session_id, "/project", "Project", connection_id)


def test_bound_delivery_never_moves_to_another_connection():
    async def run():
        original = session("codex", "one", "old")
        provider = Provider("codex", [original, session("codex", "two")])
        router = ProviderRouter([provider])
        await router.select("codex", "one")
        await router.select("codex", "two")
        await router.send_to(original, "reviewed")
        provider.available[0] = session("codex", "one", "new")
        with pytest.raises(SessionUnavailableError):
            await router.send_to(original, "stale")
        assert provider.sent == [("one", "reviewed")]

    asyncio.run(run())


def test_replaced_connection_does_not_receive_in_flight_prompt():
    async def run():
        provider = Provider("codex", [session("codex", "one", "old")])
        router = ProviderRouter([provider])
        await router.snapshot()
        provider.available = [session("codex", "one", "new")]
        with pytest.raises(SessionUnavailableError):
            await router.send("private")
        assert provider.sent == []

    asyncio.run(run())


def test_zero_one_and_multiple_targets():
    async def run():
        provider = Provider("codex")
        router = ProviderRouter([provider])
        with pytest.raises(SessionUnavailableError):
            await router.send("zero")
        provider.available = [session("codex", "one")]
        await router.send("first")
        provider.available.append(session("codex", "two"))
        await router.send("second")  # Existing selection remains stable.
        assert provider.sent == [("one", "first"), ("one", "second")]
        other = ProviderRouter([provider])
        with pytest.raises(SelectionRequiredError):
            await other.send("ambiguous")
        await other.select("codex", "two")
        await other.send("chosen")
        assert provider.sent[-1] == ("two", "chosen")

    asyncio.run(run())


def test_disappearing_target_does_not_redirect_in_flight_prompt():
    async def run():
        provider = Provider("codex", [session("codex", "one"), session("codex", "two")])
        router = ProviderRouter([provider])
        await router.select("codex", "one")
        provider.available = [session("codex", "two")]
        with pytest.raises(SessionUnavailableError):
            await router.send("private prompt")
        assert provider.sent == []
        assert (await router.snapshot()).selected == ("codex", "two")

    asyncio.run(run())


def test_provider_failure_never_implicitly_selects_another_provider():
    async def run():
        first = Provider("codex", [session("codex", "one")])
        second = Provider("claude", [session("claude", "two")])
        second.error = True
        router = ProviderRouter([first, second])
        state = await router.snapshot()
        assert state.failed_providers == ("claude",)
        assert state.selected is None
        with pytest.raises(SelectionRequiredError):
            await router.send("private")
        await router.select("codex", "one")
        await router.send("explicit")
        assert first.sent == [("one", "explicit")]

    asyncio.run(run())


def test_invalid_provider_results_and_send_errors_fail_closed():
    async def run():
        provider = Provider("codex", [session("other", "one")])
        router = ProviderRouter([provider])
        assert (await router.snapshot()).failed_providers == ("codex",)
        with pytest.raises(SessionUnavailableError):
            await router.select("other", "one")
        provider.available = [session("codex", "one")]
        provider.send_error = True
        secret = "secret prompt"
        with pytest.raises(RoutingError, match="Provider delivery failed or could not be confirmed") as error:
            await router.send(secret)
        assert secret not in str(error.value)
        assert secret not in "".join(traceback.format_exception(error.value))

    asyncio.run(run())
