"""Service and tray commands use isolated subprocess and lifecycle boundaries."""
from types import SimpleNamespace
from unittest.mock import call

import pytest
import typer

from dictare.cli import tray
from dictare.daemon import systemd
from dictare.tray import lifecycle


def test_systemd_install_and_uninstall(tmp_path, monkeypatch):
    from dictare import runtime_store

    unit = tmp_path / 'user' / systemd.UNIT_NAME
    calls = []
    monkeypatch.setattr(systemd, 'get_unit_path', lambda: unit)
    monkeypatch.setattr(runtime_store, 'resolve_service_python_path', lambda _: '/custom/python')
    monkeypatch.setattr(systemd.subprocess, 'run', lambda args, **kw: calls.append((args, kw)))
    systemd.install()
    assert 'ExecStart=/custom/python -m dictare serve' in unit.read_text()
    assert calls == [(['systemctl', '--user', 'daemon-reload'], {'check': True}),
                     (['systemctl', '--user', 'enable', systemd.UNIT_NAME], {'check': True})]
    assert systemd.is_installed()
    calls.clear()
    systemd.uninstall()
    assert not unit.exists()
    assert [args[2] for args, _ in calls] == ['disable', 'stop', 'daemon-reload']
    calls.clear()
    systemd.uninstall()
    assert not calls


def test_systemd_status_and_commands(monkeypatch):
    from unittest.mock import Mock

    run = Mock(return_value=SimpleNamespace(stdout='active\n'))
    monkeypatch.setattr(systemd.subprocess, 'run', run)
    assert systemd.is_loaded()
    run.return_value.stdout = 'inactive\n'
    assert not systemd.is_loaded()
    systemd.start()
    systemd.stop()
    assert run.call_args_list[-2:] == [call(['systemctl', '--user', 'start', systemd.UNIT_NAME], check=True),
                                      call(['systemctl', '--user', 'stop', systemd.UNIT_NAME], check=True)]


def test_tray_start_foreground_and_running(monkeypatch):
    monkeypatch.setattr(lifecycle, 'get_tray_status', lambda: SimpleNamespace(running=True, pid=42))
    with pytest.raises(typer.Exit) as exc:
        tray.tray_start(True)
    assert exc.value.exit_code == 1
    monkeypatch.setattr(lifecycle, 'get_tray_status', lambda: SimpleNamespace(running=False, pid=None))
    monkeypatch.setattr(lifecycle, 'start_tray', lambda *, foreground: 7 if foreground else 0)
    with pytest.raises(typer.Exit) as exc:
        tray.tray_start(True)
    assert exc.value.exit_code == 7


@pytest.mark.parametrize('result,running,expected', [(0, True, None), (0, False, 1), (1, False, 1)])
def test_tray_background_start(monkeypatch, result, running, expected):
    import time
    statuses = iter([SimpleNamespace(running=False), SimpleNamespace(running=running, pid=12)])
    monkeypatch.setattr(lifecycle, 'get_tray_status', lambda: next(statuses))
    monkeypatch.setattr(lifecycle, 'start_tray', lambda *, foreground: result)
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    if expected is None:
        assert tray.tray_start(False) is None
    else:
        with pytest.raises(typer.Exit) as exc:
            tray.tray_start(False)
        assert exc.value.exit_code == expected


@pytest.mark.parametrize('running,result,expected', [(False, 0, 1), (True, 0, None), (True, 1, 1)])
def test_tray_stop_and_status(monkeypatch, running, result, expected):
    monkeypatch.setattr(lifecycle, 'get_tray_status', lambda: SimpleNamespace(running=running, pid=42))
    monkeypatch.setattr(lifecycle, 'stop_tray', lambda: result)
    tray.tray_status()
    if expected is None:
        assert tray.tray_stop() is None
    else:
        with pytest.raises(typer.Exit) as exc:
            tray.tray_stop()
        assert exc.value.exit_code == expected
