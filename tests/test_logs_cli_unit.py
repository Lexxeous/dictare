"""Log command output and rotated-file behavior."""
import json

import typer
from typer.testing import CliRunner

from dictare.cli import logs


def test_reverse_chunks_and_rotated_tail(tmp_path):
    path = tmp_path / 'engine.jsonl'
    path.write_text('new one\nnew two\n')
    path.with_name('engine.jsonl.1').write_text('old one\nold two\n')
    assert list(logs._iter_lines_reverse(path, chunk_size=3)) == ['new two', 'new one']
    assert logs._tail_log_lines(path, 3) == ['old two', 'new one', 'new two']
    assert logs._tail_log_lines(path, 2, lambda line: 'one' in line) == ['old one', 'new one']
    assert logs._tail_log_lines(path, 0) == []


def test_formatting_and_filter():
    raw = json.dumps({'ts': '2026-01-01T12:34:56Z', 'level': 'warning', 'event': 'oops', 'logger': 'dictare.core', 'source': 'tray', 'count': 2})
    result = logs._format_line(raw, 'tray')
    assert '12:34:56' in result and 'WARNING' in result and '<tray>' in result and '[core]' in result and 'count=2' in result
    assert logs._format_line(raw, 'engine') is None
    assert logs._format_line('') is None
    assert 'plain text' in logs._format_line('plain text')


def test_log_command_raw_human_tts_and_missing(monkeypatch, tmp_path):
    import dictare.logging.setup as setup
    monkeypatch.setattr(setup, 'DEFAULT_LOG_DIR', tmp_path)
    app = typer.Typer()
    logs.register(app)
    runner = CliRunner()
    result = runner.invoke(app, [])
    assert result.exit_code == 1 and 'No log file found' in result.output
    entries = [{'event': 'one', 'source': 'engine'}, {'event': 'two', 'source': 'tray'}]
    (tmp_path / 'engine.jsonl').write_text('\n'.join(map(json.dumps, entries)) + '\n')
    result = runner.invoke(app, ['--raw', '--source', 'engine'])
    assert result.exit_code == 0 and 'one' in result.output and 'two' not in result.output
    result = runner.invoke(app, [])
    assert result.exit_code == 0 and 'one' in result.output and 'two' in result.output
    (tmp_path / 'tts-worker.log').write_text('hello\nworld\n')
    result = runner.invoke(app, ['--tts', '--last', '1'])
    assert result.exit_code == 0 and 'world' in result.output and 'hello' not in result.output
