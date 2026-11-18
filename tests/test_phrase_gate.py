import pytest

from dictare.core.phrase_gate import PhraseGate


def test_wake_spanning_segments_discards_prior_speech_and_preserves_prompt():
    gate = PhraseGate("Hey Dictare")
    assert not gate.accept("private words hey").capturing
    result = gate.accept("Dictare, Write a sentence.")
    assert result.capturing and result.text == "Write a sentence."
    assert gate.accept("Another sentence.").text == "Another sentence."


def test_phrase_matching_respects_word_boundaries_and_adjacent_words():
    gate = PhraseGate("hey dictare")
    for text in ("they dictare", "hey there dictare", "dictare hey"):
        assert not gate.accept(text).capturing
    assert gate.accept("HEY, DICTARE! hello").text == "hello"


def test_end_phrase_split_across_segments_buffers_and_strips():
    gate = PhraseGate("hello computer", "finish prompt")
    assert gate.accept("hello computer this is").capturing
    assert gate.accept("a test finish").text == ""
    result = gate.accept("prompt and ignore the remainder")
    assert result.completed and result.text == "this is a test"
    assert not gate.accept("another test").capturing


def test_reset_and_limit_discard_buffered_prompt():
    gate = PhraseGate("wake up", "finish now", max_chars=10)
    gate.accept("wake up private")
    gate.reset()
    assert not gate.accept("finish now").completed
    assert gate.accept("wake up way too much text").discarded
    assert gate.accept("wake up way too much text finish now").discarded
    assert not gate.accept("finish now").completed


def test_accents_use_pipeline_normalization():
    gate = PhraseGate("café ami", "fin prêt")
    result = gate.accept("CAFE ami bonjour FIN PRET")
    assert result.completed and result.text == "bonjour"


def test_partial_wake_expires(monkeypatch):
    clock = iter([10.0, 16.0])
    monkeypatch.setattr("dictare.core.phrase_gate.time.monotonic", lambda: next(clock))
    gate = PhraseGate("hey dictare")
    gate.accept("hey")
    assert not gate.accept("dictare hello").capturing


@pytest.mark.parametrize("wake,end", [("", ""), ("hello", "你好"), ("hi", "HI")])
def test_invalid_phrases_are_rejected(wake, end):
    with pytest.raises(ValueError):
        PhraseGate(wake, end)
