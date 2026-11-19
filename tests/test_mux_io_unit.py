"""Unit coverage for terminal input interception and session summaries."""
import json
import queue
import threading
from unittest.mock import Mock

from dictare.agent import mux


def test_stdin_intercepts_shortcuts_and_forwards_remaining_input(monkeypatch, tmp_path):
    data = iter([b'\x1b[I\x1c\x05\x1b[99~hello', b''])
    monkeypatch.setattr(mux.sys, 'stdin', Mock(fileno=Mock(return_value=42)))
    monkeypatch.setattr(mux.select, 'select', lambda *args: ([42], [], []))
    monkeypatch.setattr(mux.os, 'read', lambda *args: next(data))
    focus, claim, info, log = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(mux, '_report_focus', focus)
    monkeypatch.setattr(mux, '_claim_agent', claim)
    monkeypatch.setattr(mux, '_log_event', log)
    output = queue.Queue()
    counter = mux.KeystrokeCounter()
    mux._read_from_stdin(output, threading.Event(), counter, 'agent', 'http://local',
                         tmp_path / 'session', info_key_raw=b'\x05', on_info=info,
                         global_hotkey_key='f1', global_hotkey_seqs=[b'\x1b[99~'])
    assert output.get_nowait() == ('raw', b'hello')
    assert counter.count == 5
    focus.assert_called_once_with('agent', 'http://local', True)
    claim.assert_called_once_with('agent', 'http://local')
    info.assert_called_once_with()
    assert [call.args[1] for call in log.call_args_list] == ['claim_key', 'info_key', 'global_hotkey']


def test_stdin_swallows_terminal_read_error(monkeypatch):
    monkeypatch.setattr(mux.sys, 'stdin', Mock(fileno=Mock(return_value=42)))
    monkeypatch.setattr(mux.select, 'select', Mock(side_effect=OSError('closed')))
    output = queue.Queue()
    mux._read_from_stdin(output, threading.Event())
    assert output.empty()


def test_session_summary_prints_output_and_time_saved(monkeypatch, capsys):
    import random
    import urllib.request

    from dictare.utils import stats

    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps({'platform': {'stats': {
        'transcriptions': 2, 'words': 40, 'chars': 400,
        'audio_seconds': 10, 'transcription_seconds': 2, 'injection_seconds': 1,
    }}}).encode()
    monkeypatch.setattr(urllib.request, 'urlopen', Mock(return_value=response))
    monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
    monkeypatch.setattr(stats, 'load_stats', lambda: {
        'total_time_saved_seconds': 7200, 'sessions': 2, 'first_use': '2024-01-01',
    })
    mux._print_session_summary('http://local')
    result = capsys.readouterr().err
    assert 'Transcriptions' in result and 'Processing' in result
    assert '1.8 minutes extra for coffee.' in result
    assert '2.0 hours saved across 2 sessions (since Jan 01, 2024)' in result


def test_session_summary_ignores_unavailable_or_empty_stats(monkeypatch, capsys):
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', Mock(side_effect=OSError('offline')))
    mux._print_session_summary('http://local')
    assert capsys.readouterr().err == ''


def test_run_agent_starts_workers_and_cleans_up_session(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import openvip

    import dictare.config

    monkeypatch.setattr(openvip, 'Client', lambda *a, **kw: SimpleNamespace(get_status=lambda: SimpleNamespace(connected_agents=[])))
    monkeypatch.setattr(dictare.config, 'load_config', lambda: SimpleNamespace(redact=[['secret', '[redacted]']]))
    monkeypatch.setattr(mux, '_get_session_log_path', lambda agent: tmp_path / 'session')
    session_start, session_end, focus, summary = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(mux, '_write_session_start', session_start)
    monkeypatch.setattr(mux, '_write_session_end', session_end)
    monkeypatch.setattr(mux, '_report_focus', focus)
    monkeypatch.setattr(mux, '_print_session_summary', summary)
    monkeypatch.setattr(mux, 'setup_logging', lambda **kw: None)
    monkeypatch.setattr(mux, 'get_data_dir', lambda: tmp_path)
    monkeypatch.setattr(mux, '_get_winsize', lambda: (24, 80))
    session = Mock(master_fd=10)
    session.run_output_loop.return_value = 7
    monkeypatch.setattr(mux, 'PTYSession', Mock(return_value=session))
    threads = []
    class Thread:
        def __init__(self, **kwargs):
            threads.append(self)
        def start(self):
            pass
    monkeypatch.setattr(mux.threading, 'Thread', Thread)
    result = mux.run_agent('shell', ['echo', 'hello'], clear_on_start=False, startup_message='ready')
    assert result == 7
    session.start.assert_called_once_with()
    session.cleanup.assert_called_once_with()
    assert len(threads) == 3
    session_end.assert_called_once_with(tmp_path / 'session', 7, 0)
    assert [call.args[2] for call in focus.call_args_list] == [True, False]
    summary.assert_called_once()
