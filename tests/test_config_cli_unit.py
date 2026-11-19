"""Behavioral tests for configuration CLI commands."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer

from dictare.cli import config


def test_list_displays_values_and_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'get_config_path', lambda: tmp_path / 'config.toml')
    monkeypatch.setattr(config, 'load_config', lambda: object())
    monkeypatch.setattr(config, 'list_config_keys', lambda: [
        ('none', 'str', None, '', ''), ('yes', 'bool', True, '', ''),
        ('no', 'bool', False, '', ''), ('bad', 'str', '', '', ''),
        ('name', 'str', '', '', 'ENV'),
    ])
    def get_value(key, cfg):
        if key == 'bad':
            raise KeyError(key)
        return {'none': None, 'yes': True, 'no': False, 'name': 'value'}[key]
    monkeypatch.setattr(config, 'get_config_value', get_value)
    printer = Mock()
    monkeypatch.setattr(config.console, 'print', printer)
    config.config_list()
    table = printer.call_args_list[0].args[0]
    assert len(table.rows) == 5
    assert 'not created' in printer.call_args_list[1].args[0]


def test_get_and_set_success(monkeypatch):
    printer = Mock()
    setter = Mock()
    monkeypatch.setattr(config.console, 'print', printer)
    monkeypatch.setattr(config, 'get_config_value', lambda key: 42)
    monkeypatch.setattr(config, 'set_config_value', setter)
    config.config_get(Mock(), 'stt.model')
    printer.assert_called_with(42)
    config.config_set(Mock(), 'stt.model', 'small')
    setter.assert_called_once_with('stt.model', 'small')


@pytest.mark.parametrize('command, args', [(config.config_get, (None,)), (config.config_set, ('key', None))])
def test_missing_arguments_show_help(command, args, capsys):
    with pytest.raises(typer.Exit) as exc:
        command(SimpleNamespace(get_help=lambda: 'help text'), *args)
    assert exc.value.exit_code == 0
    assert 'help text' in capsys.readouterr().out


@pytest.mark.parametrize('exception', [KeyError('missing'), ValueError('invalid')])
def test_set_reports_invalid_values(monkeypatch, exception):
    setter = Mock(side_effect=exception)
    monkeypatch.setattr(config, 'set_config_value', setter)
    with pytest.raises(typer.Exit) as exc:
        config.config_set(Mock(), 'key', 'bad')
    assert exc.value.exit_code == 1


def test_get_reports_unknown_key(monkeypatch):
    monkeypatch.setattr(config, 'get_config_value', Mock(side_effect=KeyError('missing')))
    with pytest.raises(typer.Exit) as exc:
        config.config_get(Mock(), 'missing')
    assert exc.value.exit_code == 1


def test_edit_prefers_configured_editor_and_preserves_quoting(monkeypatch, tmp_path):
    path = tmp_path / 'settings.toml'
    path.touch()
    run = Mock()
    monkeypatch.setattr(config, 'get_config_path', lambda: path)
    monkeypatch.setattr(config, 'load_config', lambda path: SimpleNamespace(editor='editor --title "hello world"'))
    monkeypatch.setattr(subprocess, 'run', run)
    config.config_edit()
    run.assert_called_once_with(['editor', '--title', 'hello world', str(path)], check=True)


@pytest.mark.parametrize('error, exit_code', [(FileNotFoundError(), 1), (subprocess.CalledProcessError(7, 'editor'), 7)])
def test_edit_reports_editor_failure(monkeypatch, tmp_path, error, exit_code):
    path = tmp_path / 'settings.toml'
    path.touch()
    monkeypatch.setattr(config, 'get_config_path', lambda: path)
    monkeypatch.setattr(config, 'load_config', lambda path: SimpleNamespace(editor='editor'))
    monkeypatch.setattr(subprocess, 'run', Mock(side_effect=error))
    with pytest.raises(typer.Exit) as exc:
        config.config_edit()
    assert exc.value.exit_code == exit_code
