"""Verify generated ydotool commands without injecting real keystrokes."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.agent.injection import ydotool


def test_key_combo_ignores_unknown_keys():
    assert ydotool.parse_key_combo(" Ctrl + SHIFT + nope + Enter ") == [29, 42, 28]


def test_availability(monkeypatch):
    injector = ydotool.YdotoolInjector()
    monkeypatch.setattr(ydotool.shutil, "which", lambda _: None)
    assert not injector.is_available()
    monkeypatch.setattr(ydotool.shutil, "which", lambda _: "/fake/ydotool")
    monkeypatch.setattr("dictare.utils.platform.check_ydotool_ready", lambda: True)
    assert injector.is_available()
    assert injector.get_name() == "ydotool"


def test_ascii_text_is_sanitized_and_submitted(monkeypatch):
    injector = ydotool.YdotoolInjector()
    monkeypatch.setattr(ydotool.shutil, "which", lambda _: "/fake/ydotool")
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(ydotool.subprocess, "run", run)
    monkeypatch.setattr(ydotool.time, "sleep", Mock())
    assert injector.type_text("hi\x1b[31m!", delay_ms=5, submit_keys="ctrl+enter")
    assert run.call_args_list[0].args[0] == ["/fake/ydotool", "type", "--key-delay", "5", "--key-hold", "1", "--", "hi!"]
    assert run.call_args_list[1].args[0] == ["/fake/ydotool", "key", "29:1", "28:1", "28:0", "29:0"]
    assert injector._enter_sent


def test_unicode_and_newline(monkeypatch):
    injector = ydotool.YdotoolInjector()
    injector._ydotool_path = "/fake/ydotool"
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(ydotool.subprocess, "run", run)
    monkeypatch.setattr(ydotool.time, "sleep", Mock())
    assert injector.type_text("aé", delay_ms=2, auto_submit=False)
    assert run.call_args_list[2].args[0][-1] == "e9"
    assert run.call_args_list[-1].args[0][2:] == ["56:1", "28:1", "28:0", "56:0"]
    assert not injector._enter_sent
    assert injector.send_newline() and injector.send_submit()


@pytest.mark.parametrize("failure", [OSError("missing"), subprocess.TimeoutExpired("ydotool", 1)])
def test_subprocess_failures_are_reported(monkeypatch, failure):
    injector = ydotool.YdotoolInjector()
    injector._ydotool_path = "/fake/ydotool"
    monkeypatch.setattr(ydotool.subprocess, "run", Mock(side_effect=failure))
    assert not injector.type_text("hello")
    assert not injector._type_unicode_char("é")
    assert not injector.send_newline()
    assert not injector.send_submit()


def test_command_failure_and_missing_binary(monkeypatch):
    injector = ydotool.YdotoolInjector()
    monkeypatch.setattr(ydotool.shutil, "which", lambda _: None)
    assert not injector.type_text("hello") and not injector.send_submit() and not injector.send_newline()
    injector._ydotool_path = "/fake/ydotool"
    monkeypatch.setattr(ydotool.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=1)))
    assert not injector.type_text("hello")
    assert not injector.type_text("éa")
    assert not injector.send_submit() and not injector.send_newline()
