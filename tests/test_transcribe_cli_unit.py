"""Tests for the transcribe command and its message handling."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import openvip
import pytest
import typer

import dictare.config
from dictare.cli import transcribe


def message(text='', ops=None, **kwargs):
    return SimpleNamespace(type='transcription', text=text, x_input={'ops': ops or []}, **kwargs)


def test_messages_skip_other_types_and_flush_buffer_when_stream_ends():
    output = StringIO()
    transcribe.process_messages(iter([SimpleNamespace(type='other'), message('hello'), message('world')]), output=output)
    assert output.getvalue() == 'hello world\n'


def test_messages_flush_on_interruption():
    def stream():
        yield message('partial')
        raise KeyboardInterrupt
    output = StringIO()
    with pytest.raises(KeyboardInterrupt):
        transcribe.process_messages(stream(), output=output, verbose=True)
    assert output.getvalue() == 'partial\n'


def test_auto_submit_ignores_blank_and_emits_first_text(capsys):
    output = StringIO()
    transcribe.process_messages(iter([message('  '), message('ready'), message('ignored')]), auto_submit=True, output=output, verbose=True)
    assert output.getvalue() == 'ready\n'
    assert '[transcribe] ready' in capsys.readouterr().err


def command():
    app = typer.Typer()
    transcribe.register(app)
    return app.registered_commands[0].callback


def test_command_reports_unavailable_engine(monkeypatch):
    monkeypatch.setattr(dictare.config, 'load_config', lambda: SimpleNamespace(server=SimpleNamespace(host='localhost', port=123)))
    client = Mock()
    client.is_available.return_value = False
    factory = Mock(return_value=client)
    monkeypatch.setattr(openvip, 'Client', factory)
    with pytest.raises(typer.Exit) as exc:
        command()('agent', False, None, False)
    assert exc.value.exit_code == 1
    factory.assert_called_once_with('http://localhost:123/openvip', timeout=5)
    client.subscribe.assert_not_called()


def test_command_subscribes_with_requested_options(monkeypatch):
    monkeypatch.setattr(dictare.config, 'load_config', lambda: object())
    client = Mock()
    client.is_available.return_value = True
    client.subscribe.return_value = iter([message('done', ['submit'])])
    monkeypatch.setattr(openvip, 'Client', Mock(return_value=client))
    processor = Mock()
    monkeypatch.setattr(transcribe, 'process_messages', processor)
    command()('agent', True, 'http://example', True)
    client.subscribe.assert_called_once_with('agent', reconnect=True)
    assert processor.call_args.kwargs == {'auto_submit': True, 'verbose': True}


def test_command_handles_interruption(monkeypatch):
    monkeypatch.setattr(dictare.config, 'load_config', lambda: object())
    client = Mock()
    client.is_available.return_value = True
    client.subscribe.side_effect = KeyboardInterrupt
    monkeypatch.setattr(openvip, 'Client', Mock(return_value=client))
    command()('agent', False, 'http://example', False)
