"""Worker startup and pre-caching behavior without subprocesses or audio."""

from unittest.mock import MagicMock

import pytest

from dictare.core.tts_manager import TTSManager


def manager():
    config = MagicMock()
    config.tts.engine = "piper"
    config.tts.language = "en"
    config.tts.speed = 1
    config.tts.voice = "voice"
    return TTSManager(config)


def test_worker_load_success_records_duration(monkeypatch):
    mgr = manager()
    spawn = MagicMock()
    save = MagicMock()
    monkeypatch.setattr(mgr, "_spawn_worker", spawn)
    monkeypatch.setattr("dictare.utils.stats.save_model_load_time", save)
    server = object()
    mgr.load(http_server=server, estimated=5)
    spawn.assert_called_once_with(server)
    assert mgr.loading_status["status"] == "done"
    assert mgr.loading_status["estimated"] == 5
    assert save.call_args.args[0] == "piper"


def test_worker_load_failure_clears_engine_and_records_error(monkeypatch):
    mgr = manager()
    mgr._tts_engine = object()
    mgr._tts_proxy = object()
    monkeypatch.setattr(mgr, "_spawn_worker", MagicMock(side_effect=RuntimeError("bad worker")))
    mgr.load(http_server=object())
    assert mgr.loading_status["status"] == "error"
    assert mgr.error == "bad worker"
    assert mgr.engine is None and mgr._tts_proxy is None


def test_worker_early_exit_reports_stderr(monkeypatch):
    mgr = manager()
    server = MagicMock(port=1234)
    server.is_tts_connected.return_value = False
    process = MagicMock(returncode=7)
    process.poll.return_value = 7
    process.stderr.read.return_value = b"missing dependency"
    monkeypatch.setattr("dictare.tts.venv.get_venv_python", lambda _: None)
    monkeypatch.setattr("dictare.core.tts_manager.subprocess.Popen", lambda *a, **kw: process)
    with pytest.raises(RuntimeError, match="code 7: missing dependency"):
        mgr._spawn_worker(server)
    assert not mgr._worker_ready


def test_worker_connection_timeout(monkeypatch):
    mgr = manager()
    server = MagicMock(port=1234)
    server.is_tts_connected.return_value = False
    process = MagicMock()
    process.poll.return_value = None
    clock = iter([0, 121])
    monkeypatch.setattr("dictare.tts.venv.get_venv_python", lambda _: None)
    monkeypatch.setattr("dictare.core.tts_manager.subprocess.Popen", lambda *a, **kw: process)
    monkeypatch.setattr("dictare.core.tts_manager.time.monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="failed to connect"):
        mgr._spawn_worker(server)
    server.wait_tts_connected.assert_not_called()


def test_precache_skips_hits_and_continues_after_errors(monkeypatch):
    mgr = manager()
    engine = MagicMock()
    engine.check_cache.side_effect = [True, False, RuntimeError("cache failure"), False]
    engine.speak.side_effect = [True, False]
    mgr._tts_engine = engine
    class InlineThread:
        def __init__(self, *, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr("dictare.core.tts_manager.threading.Thread", InlineThread)
    mgr.precache_phrases(["cached", "new", "broken", "failed"])
    assert engine.speak.call_count == 2
    engine.speak.assert_any_call("new", play=False)
    engine.speak.assert_any_call("failed", play=False)
