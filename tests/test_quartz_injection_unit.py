"""Quartz injector event generation with an in-memory CoreGraphics substitute."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.agent.injection import quartz


@pytest.fixture
def fake_quartz(monkeypatch):
    module = SimpleNamespace(
        kCGEventFlagMaskShift=1, kCGEventFlagMaskAlternate=2,
        kCGEventFlagMaskControl=4, kCGEventFlagMaskCommand=8,
        kCGEventSourceStateHIDSystemState=10, kCGSessionEventTap=20,
        CGEventSourceCreate=Mock(return_value="source"),
        CGEventCreateKeyboardEvent=Mock(side_effect=lambda source, code, down: (code, down)),
        CGEventKeyboardSetUnicodeString=Mock(), CGEventPost=Mock(), CGEventSetFlags=Mock(),
    )
    monkeypatch.setitem(sys.modules, "Quartz", module)
    monkeypatch.setattr(quartz.sys, "platform", "darwin")
    monkeypatch.setattr(quartz, "time", SimpleNamespace(sleep=Mock()))
    return module


def test_combo_parsing_and_event_generation(fake_quartz):
    assert quartz.parse_macos_key_combo("shift+option+control+cmd+return") == (15, 36)
    injector = quartz.QuartzInjector()
    assert injector.is_available() and injector.is_available()
    fake_quartz.CGEventSourceCreate.assert_called_once()
    assert injector.type_text("é\x1b[31m!", delay_ms=2, auto_submit=False)
    assert [call.args[2] for call in fake_quartz.CGEventKeyboardSetUnicodeString.call_args_list] == ["é", "!"]
    fake_quartz.CGEventSetFlags.assert_called_with((36, True), 1)
    assert injector.send_newline() and injector.send_submit()
    assert injector.get_name() == "macos-quartz"


def test_unavailable_source_and_errors(fake_quartz):
    fake_quartz.CGEventSourceCreate.return_value = None
    injector = quartz.QuartzInjector()
    assert not injector.is_available()
    assert not injector.type_text("hello")
    assert not injector.send_newline()
    assert not injector.send_submit()
    fake_quartz.CGEventSourceCreate.side_effect = OSError("denied")
    assert not injector.type_text("hello")
    assert not injector.send_newline()
    assert not injector.send_submit()


def test_missing_framework_and_wrong_platform(monkeypatch):
    monkeypatch.setattr(quartz.sys, "platform", "linux")
    with pytest.raises(RuntimeError):
        quartz.QuartzInjector()
    monkeypatch.setattr(quartz.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "Quartz", None)
    assert quartz.parse_macos_key_combo("shift+enter") == (0, 36)
    injector = quartz.QuartzInjector()
    assert not injector.is_available()
    assert not injector.type_text("text")
    assert not injector.send_newline() and not injector.send_submit()
