from dictare.agent.managed_session import ManagedSessionAgent
from dictare.agent.provider_routing import ProviderSession


def test_incremental_dictation_submits_to_the_bound_connection():
    session = ProviderSession("codex", "session", "/work", "Example", "connection")
    deliveries = []
    agent = ManagedSessionAgent(session, lambda target, text: deliveries.append((target, text)) or True)
    assert agent.send({"text": "first", "x_input": {"ops": ["newline"]}})
    assert agent.snapshot() == ("first", False)
    assert agent.send({"text": "second", "x_input": {"ops": ["submit"]}})
    assert deliveries == [(session, "first\nsecond")]
    assert agent.snapshot() == ("", False)


def test_failed_delivery_is_not_retried_and_review_binding_expires():
    session = ProviderSession("codex", "session", "/work", "Example", "connection")
    attempts = []
    agent = ManagedSessionAgent(session, lambda target, text: attempts.append(text) and True)
    bound = agent.bind_for_review()
    assert not bound.send({"text": "once", "x_input": {"ops": ["submit"]}})
    assert not bound.send({"text": "again", "x_input": {"ops": ["submit"]}})
    assert attempts == ["once"]
    assert agent.snapshot() == ("once", True)
    agent.close()
    assert not bound.send({"text": "later"})
