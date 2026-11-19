"""Keyboard capture behavior with a simulated pynput listener."""
import sys
from types import SimpleNamespace

import pytest

from dictare.cli.shortcuts import _capture_shortcut


@pytest.mark.parametrize('modifier,key,expected', [('ctrl_l', SimpleNamespace(char='a'), 'Ctrl+A'), ('alt_r', SimpleNamespace(name='f2'), 'Alt+F2'), ('shift', SimpleNamespace(char='x'), 'Shift+X'), ('cmd', SimpleNamespace(char='z'), 'Cmd+Z')])
def test_capture_modifier_and_key(monkeypatch, modifier, key, expected):
    names = ['esc', 'ctrl_l', 'ctrl_r', 'ctrl', 'alt_l', 'alt_r', 'alt', 'alt_gr', 'shift_l', 'shift_r', 'shift', 'cmd_l', 'cmd_r', 'cmd']
    keys = SimpleNamespace(**{name: object() for name in names})
    class Listener:
        def __init__(self, on_press, on_release):
            self.press, self.release = on_press, on_release
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def join(self):
            assert self.press(getattr(keys, modifier)) is None
            assert self.press(key) is False
            self.release(getattr(keys, modifier))
    monkeypatch.setitem(sys.modules, 'pynput', SimpleNamespace(keyboard=SimpleNamespace(Key=keys, Listener=Listener)))
    assert _capture_shortcut() == expected


def test_missing_pynput_cancels(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pynput', None)
    assert _capture_shortcut() is None
