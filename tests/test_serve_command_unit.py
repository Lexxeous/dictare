"""Foreground command startup decisions, without starting services."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from typer import Typer
from typer.testing import CliRunner

from dictare.cli import serve


def test_serve_recovers_stale_pid_and_starts_controller(tmp_path, monkeypatch):
    import dictare.app
    import dictare.utils.paths

    pid_file = tmp_path / "engine.pid"
    pid_file.write_text("not a pid")
    monkeypatch.setattr(dictare.utils.paths, "get_pid_path", lambda: pid_file)
    config = SimpleNamespace(log_level="info", stt=SimpleNamespace(hw_accel=False))
    monkeypatch.setattr(serve, "load_config", lambda _: config)
    download = Mock()
    monkeypatch.setattr(serve, "ensure_required_models", download)
    detect = Mock()
    monkeypatch.setattr(serve, "auto_detect_acceleration", detect)
    controller = Mock()
    monkeypatch.setattr(dictare.app, "AppController", lambda cfg: controller)
    run = Mock()
    monkeypatch.setattr(serve, "_run_serve", run)

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target
        def start(self):
            self.target()

    monkeypatch.setattr("threading.Thread", ImmediateThread)
    app = Typer()
    serve.register(app)
    result = CliRunner().invoke(app, ["--verbose"])
    assert result.exit_code == 0, result.output
    assert not pid_file.exists()
    assert config.log_level == "debug"
    download.assert_called_once_with(config)
    detect.assert_called_once_with(config, cpu_only=True)
    assert run.call_args.args[:2] == (controller, config)
    assert run.call_args.kwargs == {"verbose": True}


def test_serve_existing_pid_does_not_start_engine(tmp_path, monkeypatch):
    import os

    import dictare.utils.paths

    pid_file = tmp_path / "engine.pid"
    pid_file.write_text("42")
    monkeypatch.setattr(dictare.utils.paths, "get_pid_path", lambda: pid_file)
    kill = Mock()
    monkeypatch.setattr(os, "kill", kill)
    load = Mock()
    monkeypatch.setattr(serve, "load_config", load)
    app = Typer()
    serve.register(app)
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0
    assert "already running" in result.output
    kill.assert_called_once_with(42, 0)
    load.assert_not_called()
    assert Path(pid_file).exists()


def test_run_serve_starts_and_stops_ipc_and_controller(tmp_path, monkeypatch):
    import logging
    import signal
    import sys

    import pytest

    import dictare.hotkey.ipc
    import dictare.logging.setup
    import dictare.utils.paths

    class ExitCalledError(Exception):
        pass

    fake_os = SimpleNamespace(environ={"DICTARE_DEV_MODE": "1"}, getpid=lambda: 123)
    fake_os._exit = Mock(side_effect=ExitCalledError)
    fake_os.kill = Mock()
    monkeypatch.setattr(dictare.logging.setup, "get_default_log_path", lambda _: tmp_path / "engine.log")
    setup = Mock()
    monkeypatch.setattr(dictare.logging.setup, "setup_logging", setup)
    pid_path = tmp_path / "pid"
    pid_path.write_text("123")
    monkeypatch.setattr(dictare.utils.paths, "get_pid_path", lambda: pid_path)
    handlers = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.update({sig: handler}))
    ipc = Mock()
    monkeypatch.setattr(dictare.hotkey.ipc, "HotkeyIPCServer", Mock(return_value=ipc))
    controller = Mock(exit_code=0)
    original_stderr = sys.stderr
    logger = logging.getLogger("dictare")
    original_handlers = logger.handlers[:]
    try:
        with pytest.raises(ExitCalledError):
            serve._run_serve(controller, SimpleNamespace(log_level="info", server=SimpleNamespace(port=9999)), fake_os)
    finally:
        sys.stderr = original_stderr
        logger.handlers[:] = original_handlers
    controller.start.assert_called_once_with(start_listening=False, mode="serve", with_bindings=False)
    controller.run.assert_called_once()
    controller.stop.assert_called_once()
    ipc.start.assert_called_once()
    ipc.stop.assert_called_once()
    assert not pid_path.exists()
    fake_os._exit.assert_called_once_with(0)
    handlers[signal.SIGTERM](signal.SIGTERM, None)
    controller.request_shutdown.assert_called_once()
    if hasattr(signal, "SIGUSR1"):
        handlers[signal.SIGUSR1](signal.SIGUSR1, None)
        controller.on_hotkey_tap.assert_called_once()
    assert setup.call_args.kwargs["params"] == {"mode": "serve", "pid": 123}


def test_run_serve_failed_start_exits_nonzero_and_cleans_up(tmp_path, monkeypatch):
    import logging
    import signal
    import sys

    import pytest

    import dictare.logging.setup
    import dictare.utils.paths

    class ExitCalledError(Exception):
        pass

    fake_os = SimpleNamespace(environ={"DICTARE_DEV_MODE": "1", "DICTARE_HOTKEY_TRANSPORT": "signal"}, getpid=lambda: 3)
    fake_os._exit = Mock(side_effect=ExitCalledError)
    fake_os.kill = Mock()
    monkeypatch.setattr(dictare.logging.setup, "get_default_log_path", lambda _: tmp_path / "log")
    monkeypatch.setattr(dictare.logging.setup, "setup_logging", Mock())
    monkeypatch.setattr(dictare.utils.paths, "get_pid_path", lambda: tmp_path / "missing")
    monkeypatch.setattr(signal, "signal", Mock())
    controller = Mock(exit_code=0)
    controller.start.side_effect = RuntimeError("startup failed")
    original_stderr = sys.stderr
    logger = logging.getLogger("dictare")
    original_handlers = logger.handlers[:]
    try:
        with pytest.raises(ExitCalledError):
            serve._run_serve(controller, SimpleNamespace(log_level="warning", server=SimpleNamespace(port=1)), fake_os)
    finally:
        sys.stderr = original_stderr
        logger.handlers[:] = original_handlers
    controller.run.assert_not_called()
    controller.stop.assert_called_once()
    fake_os._exit.assert_called_once_with(1)
