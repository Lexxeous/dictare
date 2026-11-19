"""Behavior checks for phonetic matching and edit distance edge cases."""

import pytest

from dictare.utils.jellyfish import levenshtein_distance, metaphone


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("", ""), ("123-!", ""), ("knight", "NT"), ("dumb", "TM"),
        ("cia", "X"), ("school", "SKL"), ("church", "XRX"),
        ("edge", "EJ"), ("gnome", "NM"), ("phone", "FN"),
        ("queen", "KN"), ("ship", "XP"), ("nation", "NXN"),
        ("thin", "0N"), ("vex", "FKS"), ("zoo", "S"),
        ("yellow", "YL"), ("cat", "KT"), ("dog", "TK"),
    ],
)
def test_metaphone_rules(word, expected):
    assert metaphone(word) == expected


@pytest.mark.parametrize(
    ("left", "right", "distance"),
    [("", "abc", 3), ("kitten", "sitting", 3), ("abc", "abc", 0),
     ("book", "back", 2), ("a", "", 1)],
)
def test_edit_distance_is_symmetric(left, right, distance):
    assert levenshtein_distance(left, right) == distance
    assert levenshtein_distance(right, left) == distance
