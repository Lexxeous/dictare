"""Single-draft review ownership and delivery coordination."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from dictare.core.prompt_review import ReviewSlot


class Destination:
    def __init__(self, name: str) -> None:
        self.id = name

    def send(self, message: dict) -> bool:
        return True


def test_review_freezes_destination_and_isolates_message_copies():
    slot = ReviewSlot()
    first = Destination("first")
    messages = [{"text": "hello", "x_input": {"ops": ["submit"]}}]
    draft = slot.hold(first, messages)
    assert draft is not None
    messages[0]["x_input"]["ops"].clear()
    draft.messages[0]["text"] = "modified"
    claim = slot.claim(draft.id)
    assert claim is not None
    assert claim.agent is first
    assert claim.messages == [{"text": "hello", "x_input": {"ops": ["submit"]}}]
    assert "hello" not in repr(claim)


def test_only_one_draft_and_stale_actions_cannot_remove_later_draft():
    slot = ReviewSlot()
    first = slot.hold(Destination("one"), [{"text": "first"}])
    assert first is not None
    assert slot.hold(Destination("two"), [{"text": "second"}]) is None
    assert slot.discard(first.id)
    second = slot.hold(Destination("two"), [{"text": "second"}])
    assert second is not None
    assert not slot.discard(first.id)
    assert slot.claim(first.id) is None
    assert slot.snapshot() == second


def test_send_claims_are_exclusive_and_failure_retains_unsent_messages():
    slot = ReviewSlot()
    draft = slot.hold(Destination("agent"), [{"text": "first"}, {"text": "second"}])
    assert draft is not None
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: slot.claim(draft.id), range(20)))
    claimed = [claim for claim in claims if claim is not None]
    assert len(claimed) == 1
    assert not slot.discard(draft.id)
    assert slot.finish(claimed[0], 1)
    assert slot.snapshot().messages == [{"text": "second"}]
    retry = slot.claim(draft.id)
    assert retry is not None
    assert not slot.finish(claimed[0], 1)
    assert slot.finish(retry, 0)
    assert slot.snapshot().messages == [{"text": "second"}]
    retry = slot.claim(draft.id)
    assert retry is not None and slot.finish(retry, 1)
    assert slot.snapshot() is None


def test_invalid_completion_does_not_release_claim():
    slot = ReviewSlot()
    draft = slot.hold(Destination("agent"), [{"text": "hello"}])
    assert draft is not None
    claim = slot.claim(draft.id)
    assert claim is not None
    with pytest.raises(ValueError):
        slot.finish(claim, 2)
    assert slot.claim(draft.id) is None
    assert slot.finish(claim, 0)
    assert slot.discard(draft.id)
