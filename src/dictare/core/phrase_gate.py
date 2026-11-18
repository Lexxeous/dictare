"""Bounded, local transcript gating for experimental capture modes.

This module has no side effects. Its owner must serialize access, reset it when
capture is invalidated, and check the capture generation before using output.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from dictare.pipeline.filters._text import match_pattern, tokenize


def _tokens_with_spans(text: str) -> list[tuple[str, int, int]]:
    # Normalize each original character separately so matches can be stripped
    # from the original transcript without losing its spelling or punctuation.
    normalized: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        for item in unicodedata.normalize("NFD", char.lower()):
            if unicodedata.category(item) != "Mn":
                normalized.append(item)
                offsets.append(index)
    return [
        (match.group(), offsets[match.start()], offsets[match.end() - 1] + 1)
        for match in re.finditer(r"[a-zA-Z0-9]+", "".join(normalized))
    ]


def _find(text: str, phrase: list[str]) -> tuple[int, int] | None:
    words = _tokens_with_spans(text)
    for index in range(len(words) - len(phrase) + 1):
        window = [word[0] for word in words[index:index + len(phrase)]]
        if match_pattern(window, phrase, 0) is not None:
            return words[index][1], words[index + len(phrase) - 1][2]
    return None


@dataclass(frozen=True)
class PhraseResult:
    text: str = ""
    capturing: bool = False
    completed: bool = False
    discarded: bool = False


class PhraseGate:
    """Wait for a wake phrase and optionally buffer until an end phrase.

    Phrase words must be adjacent: unlike command matching, unrelated speech
    between words must never start recording. Waiting retains only a possible
    partial wake phrase, and bounded capture fails closed on excessive text.
    """

    def __init__(
        self, wake: str, end: str = "", *, max_chars: int = 32000,
        partial_timeout: float = 5.0,
    ) -> None:
        self._wake = tokenize(wake)
        self._end = tokenize(end)
        for phrase in (wake, end):
            for char in unicodedata.normalize("NFD", phrase):
                if char.isalpha() and not (char.isascii() and char.isalpha()):
                    raise ValueError("Phrases support Latin letters and digits only")
        if not self._wake or (end.strip() and not self._end):
            raise ValueError("Phrases must contain supported words")
        if len(self._wake) > 10 or len(self._end) > 10 or max_chars < 1 or partial_timeout <= 0:
            raise ValueError("Invalid phrase length or capture limit")
        if self._end == self._wake:
            raise ValueError("Wake and end phrases must differ")
        self._max_chars = max_chars
        self._partial_timeout = partial_timeout
        self.reset()

    def reset(self) -> None:
        self._capturing = False
        self._pending = ""
        self._partial_at = 0.0

    @property
    def capturing(self) -> bool:
        return self._capturing

    def accept(self, segment: str) -> PhraseResult:
        if not self._capturing and self._pending and time.monotonic() - self._partial_at > self._partial_timeout:
            self._pending = ""
        text = " ".join(part for part in (self._pending, segment.strip()) if part)
        self._pending = ""
        if not self._capturing:
            match = _find(text, self._wake)
            if match is None:
                words = _tokens_with_spans(text)
                # Only retain a suffix that could complete the wake phrase.
                for count in range(min(len(words), len(self._wake) - 1), 0, -1):
                    if [word[0] for word in words[-count:]] == self._wake[:count]:
                        self._pending = text[words[-count][1]:]
                        self._partial_at = time.monotonic()
                        break
                return PhraseResult()
            self._capturing = True
            text = text[match[1]:].lstrip(" ,.!?:;\t\n")

        if self._end:
            match = _find(text, self._end)
            if match is not None:
                result = text[:match[0]].strip()
                self.reset()
                if len(result) > self._max_chars:
                    return PhraseResult(discarded=True)
                return PhraseResult(text=result, completed=True)
            if len(text) > self._max_chars:
                self.reset()
                return PhraseResult(discarded=True)
            self._pending = text
            return PhraseResult(capturing=True)

        return PhraseResult(text=text.strip(), capturing=True)
