"""Tests for CLI entry-point registration and configuration errors."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer

import dictare.cli as cli
from dictare.config import ConfigError


def test_version_callback_prints_and_exits(monkeypatch):
    printer = Mock()
    monkeypatch.setattr(cli.console, "print", printer)
    cli.version_callback(False)
    printer.assert_not_called()
    with pytest.raises(typer.Exit):
        cli.version_callback(True)
    assert cli.__version__ in printer.call_args.args[0]


def test_version_lists_installed_and_missing_dependencies(monkeypatch):
    import importlib.metadata

    printer = Mock()
    monkeypatch.setattr(cli.console, "print", printer)
    def version(name):
        if name == "openvip":
            return "1.2"
        raise importlib.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(importlib.metadata, "version", version)
    cli.version(deps=True)
    output = " ".join(call.args[0] for call in printer.call_args_list)
    assert "openvip 1.2" in output
    assert "faster-whisper" in output and "not installed" in output


def test_plugin_registration_loads_commands_and_continues_after_failure(monkeypatch, caplog):
    import dictare.plugins
    import dictare.services

    commands = typer.Typer()
    plugin = SimpleNamespace(name="example", description="Example", on_load=Mock(), get_commands=Mock(return_value=commands))
    class Broken:
        def __init__(self):
            raise RuntimeError("broken plugin")
    monkeypatch.setattr(dictare.plugins, "discover_plugins", lambda: [Broken, lambda: plugin])
    registry = object()
    monkeypatch.setattr(dictare.services, "ServiceRegistry", lambda: registry)
    add = Mock()
    monkeypatch.setattr(cli.app, "add_typer", add)
    cli._register_plugins()
    plugin.on_load.assert_called_once_with(registry)
    add.assert_called_once_with(commands, name="example", help="Example")
    assert "broken plugin" in caplog.text


def test_ensure_plugins_registered_once(monkeypatch):
    register = Mock()
    monkeypatch.setattr(cli, "_plugins_registered", False)
    monkeypatch.setattr(cli, "_register_plugins", register)
    cli._ensure_plugins_registered()
    cli._ensure_plugins_registered()
    register.assert_called_once()


def test_main_reports_configuration_error(monkeypatch):
    check = Mock()
    register = Mock()
    printer = Mock()
    def fail():
        raise ConfigError("invalid setting")
    monkeypatch.setattr(cli.misc, "check_python_environment", check)
    monkeypatch.setattr(cli, "_ensure_plugins_registered", register)
    monkeypatch.setattr(cli, "app", fail)
    monkeypatch.setattr(cli.console, "print", printer)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert "invalid setting" in printer.call_args.args[0]
    check.assert_called_once()
    register.assert_called_once()
