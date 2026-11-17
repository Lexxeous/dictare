"""Reviewed prompts keep their destination and require explicit delivery."""

from dictare.config import Config
from dictare.core.engine import DictareEngine


class Destination:
    def __init__(self, name, outcomes):
        self.id = name
        self.outcomes = iter(outcomes)
        self.received = []

    def send(self, message):
        self.received.append(message)
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result


def test_review_send_retains_unsent_remainder_and_does_not_retarget():
    engine = DictareEngine(Config(), hotkey_enabled=False)
    target = Destination("codex", [True, False, True])
    other = Destination("other", [True])
    draft = engine._review_slot.hold(target, [{"text": "one"}, {"text": "two"}])
    assert draft is not None
    engine._agent_mgr._agents[other.id] = other
    engine._agent_mgr._current_agent_id = other.id
    assert engine.send_review(draft.id) == "partial"
    assert engine.review_snapshot().messages == [{"text": "two"}]
    assert engine.send_review(draft.id) == "scheduled"
    assert [message["text"] for message in target.received] == ["one", "two", "two"]
    assert other.received == []
    assert engine.review_snapshot() is None
    assert engine.send_review(draft.id) == "unavailable"


def test_failed_or_discarded_review_never_sends_automatically(caplog):
    engine = DictareEngine(Config(), hotkey_enabled=False)
    target = Destination("codex", [RuntimeError("private transcript")])
    draft = engine._review_slot.hold(target, [{"text": "private transcript"}])
    assert draft is not None
    assert target.received == []
    assert engine.send_review(draft.id) == "failed"
    assert engine.review_snapshot().id == draft.id
    assert "private transcript" not in caplog.text
    assert engine.discard_review(draft.id)
    assert engine.review_snapshot() is None
