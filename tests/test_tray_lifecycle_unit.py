"""Tray process lifecycle tests use fake process and PID state."""

import signal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.tray import lifecycle


def test_pid_status_and_stale_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, "get_dictare_data_dir", lambda: tmp_path / "data")
    assert lifecycle.read_pid() is None
    lifecycle.write_pid(123)
    assert lifecycle.read_pid() == 123
    monkeypatch.setattr(lifecycle.os, "kill", Mock())
    assert lifecycle.get_tray_status() == lifecycle.TrayStatus(True, 123)
    monkeypatch.setattr(lifecycle.os, "kill", Mock(side_effect=OSError()))
    assert lifecycle.get_tray_status() == lifecycle.TrayStatus(False)
    assert lifecycle.read_pid() is None
    lifecycle.get_pid_path().write_text("invalid")
    assert lifecycle.read_pid() is None
    lifecycle.remove_pid()
    lifecycle.remove_pid()


@pytest.mark.parametrize("platform,exited", [("darwin", False), ("linux", False), ("linux", True)])
def test_background_start_checks_child(platform, exited, monkeypatch):
    monkeypatch.setattr(lifecycle.sys, "platform", platform)
    monkeypatch.setattr(lifecycle, "get_tray_status", lambda: lifecycle.TrayStatus(False))
    process = SimpleNamespace(pid=234, poll=lambda: 1 if exited else None)
    popen = Mock(return_value=process)
    monkeypatch.setattr(lifecycle.subprocess, "Popen", popen)
    monkeypatch.setattr(lifecycle, "time", SimpleNamespace(sleep=Mock()))
    write = Mock()
    monkeypatch.setattr(lifecycle, "write_pid", write)
    assert lifecycle.start_tray() == int(exited)
    assert popen.call_args.kwargs["start_new_session"] is True
    assert write.call_args_list == ([] if exited else [((234,), {})])


def test_foreground_start_and_already_running(monkeypatch):
    import dictare.tray.app

    main = Mock()
    monkeypatch.setattr(dictare.tray.app, "main", main)
    monkeypatch.setattr(lifecycle, "get_tray_status", lambda: lifecycle.TrayStatus(False))
    assert lifecycle.start_tray(foreground=True) == 0
    main.assert_called_once()
    monkeypatch.setattr(lifecycle, "get_tray_status", lambda: lifecycle.TrayStatus(True, 1))
    assert lifecycle.start_tray() == 1


def test_stop_escalates_and_removes_pid(monkeypatch):
    monkeypatch.setattr(lifecycle, "get_tray_status", lambda: lifecycle.TrayStatus(True, 123))
    monkeypatch.setattr(lifecycle, "is_process_running", lambda _: True)
    kill, remove = Mock(), Mock()
    monkeypatch.setattr(lifecycle.os, "kill", kill)
    monkeypatch.setattr(lifecycle, "remove_pid", remove)
    monkeypatch.setattr(lifecycle, "time", SimpleNamespace(sleep=Mock()))
    assert lifecycle.stop_tray() == 0
    assert [call.args[1] for call in kill.call_args_list] == [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]
    remove.assert_called_once()
    monkeypatch.setattr(lifecycle, "get_tray_status", lambda: lifecycle.TrayStatus(False))
    assert lifecycle.stop_tray() == 1
