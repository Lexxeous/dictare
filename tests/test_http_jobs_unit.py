"""Install and download job state transitions without network or installation."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.core.http_server import OpenVIPServer


@pytest.fixture
def job_server(monkeypatch):
    import time
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    server = OpenVIPServer.__new__(OpenVIPServer)
    server.download_jobs = {}
    server.progress_queues_lock = threading.Lock()
    events = []
    server.progress_queues = [SimpleNamespace(put_nowait=events.append)]
    loop = SimpleNamespace(call_soon_threadsafe=lambda fn, value: fn(value))
    return server, loop, events


@pytest.mark.parametrize('ok', [True, False])
def test_tts_install_job_reports_progress_and_result(monkeypatch, job_server, ok):
    import dictare.tts.venv as venv
    server, loop, events = job_server
    def install(name, on_progress):
        on_progress('preparing')
        return ok
    monkeypatch.setattr(venv, 'install_venv', install)
    server.run_tts_install('kokoro', loop)
    assert [event['status'] for event in events] == ['downloading', 'downloading', 'done' if ok else 'error']
    assert events[1]['message'] == 'preparing'
    assert server.download_jobs == {}


def test_capability_venv_failure_and_cached_success(monkeypatch, job_server):
    import dictare.tts.venv as venv
    import dictare.utils.hf_download as download
    server, loop, events = job_server
    monkeypatch.setattr(venv, 'is_venv_installed', lambda name: False)
    monkeypatch.setattr(venv, 'install_venv', lambda name, on_progress: False)
    server.run_capability_install('voice', {'venv': 'voice'}, loop)
    assert events[-1]['status'] == 'error' and 'Venv install failed' in events[-1]['message']
    events.clear()
    monkeypatch.setattr(venv, 'is_venv_installed', lambda name: True)
    monkeypatch.setattr(download, 'is_repo_cached', lambda repo, check: True)
    server.run_capability_install('voice', {'venv': 'voice', 'repo': 'cached'}, loop)
    assert events[-1]['status'] == 'done'
    assert server.download_jobs == {}


@pytest.mark.parametrize('fail', [False, True])
def test_download_job_reports_completion(monkeypatch, job_server, fail):
    import huggingface_hub

    import dictare.utils.hf_download as download
    server, loop, events = job_server
    monkeypatch.setattr(download, 'get_repo_size', lambda repo: 100)
    monkeypatch.setattr(download, 'get_cache_size', lambda repo: 100)
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', Mock(side_effect=OSError('offline') if fail else None))
    server.run_model_download('model', {'repo': 'test/repo', 'size_gb': 1}, loop)
    assert events[0]['status'] == 'downloading'
    assert events[-1]['status'] == ('error' if fail else 'done')
    assert events[-1]['total_bytes'] == 100
    assert server.download_jobs == {}


@pytest.mark.parametrize('fail', [False, True])
def test_capability_download_after_venv_install(monkeypatch, job_server, fail):
    import huggingface_hub

    import dictare.tts.venv as venv
    import dictare.utils.hf_download as download
    server, loop, events = job_server
    monkeypatch.setattr(venv, 'is_venv_installed', lambda name: False)
    def install(name, on_progress):
        on_progress('creating')
        return True
    monkeypatch.setattr(venv, 'install_venv', install)
    monkeypatch.setattr(download, 'is_repo_cached', lambda repo, check: False)
    monkeypatch.setattr(download, 'get_repo_size', lambda repo: 500)
    monkeypatch.setattr(download, 'get_cache_size', lambda repo: 500)
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', Mock(side_effect=OSError('offline') if fail else None))
    server.run_capability_install('voice', {'venv': 'voice', 'repo': 'test/repo', 'size_gb': 1}, loop)
    assert any(event.get('message') == 'creating' for event in events)
    assert any(event.get('message') == 'Downloading model...' for event in events)
    assert events[-1]['status'] == ('error' if fail else 'done')
    assert server.download_jobs == {}
