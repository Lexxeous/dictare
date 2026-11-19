"""Whisper downloads handle cache, network errors, and credential restoration."""

from contextlib import nullcontext
from unittest.mock import Mock

import huggingface_hub
import pytest
import rich.progress
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError

from dictare.stt.faster_whisper import _download_model_with_progress
from dictare.utils import hf_download


@pytest.fixture
def download_services(monkeypatch):
    monkeypatch.setattr(rich.progress, 'Progress', lambda *args, **kwargs: nullcontext(Mock()))
    download = Mock(return_value='/models/base')
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', download)
    monkeypatch.setattr(hf_download, 'is_repo_cached', Mock(return_value=False))
    monkeypatch.setattr(hf_download, 'get_repo_size', Mock(return_value=None))
    monitor = Mock(side_effect=lambda *args: nullcontext())
    monkeypatch.setattr(hf_download, 'DownloadProgressMonitor', monitor)
    return download, monitor


def test_turbo_and_cached_models_avoid_network(download_services, monkeypatch):
    download, _ = download_services
    assert _download_model_with_progress('turbo') == 'turbo'
    download.assert_not_called()
    monkeypatch.setattr(hf_download, 'is_repo_cached', Mock(return_value=True))
    assert _download_model_with_progress('base') == '/models/base'
    download.assert_called_once_with('Systran/faster-whisper-base', local_files_only=True)


def test_download_uses_public_access_and_restores_tokens(download_services, monkeypatch):
    download, monitor = download_services
    monkeypatch.setenv('HF_TOKEN', 'old-token')
    monkeypatch.setenv('HF_HUB_TOKEN', 'other-token')
    def check_credentials(*args, **kwargs):
        import os
        assert 'HF_TOKEN' not in os.environ and 'HF_HUB_TOKEN' not in os.environ
        return '/models/base'
    download.side_effect = check_credentials
    console = Mock()
    assert _download_model_with_progress('base', console) == '/models/base'
    assert download.call_args.kwargs == {'local_files_only': False, 'token': False}
    assert monitor.call_args.args[1] == 145 * 1024 * 1024
    import os
    assert os.environ['HF_TOKEN'] == 'old-token'
    assert os.environ['HF_HUB_TOKEN'] == 'other-token'
    assert any('successfully' in str(c) for c in console.print.call_args_list)


@pytest.mark.parametrize(('error', 'message', 'hint'), [
    (RepositoryNotFoundError('401 Unauthorized', response=Mock()), 'not found', 'Authentication error'),
    (RepositoryNotFoundError('404', response=Mock()), 'not found', '404'),
    (HfHubHTTPError('401 Unauthorized', response=Mock()), 'Failed to download', 'Authentication error'),
    (HfHubHTTPError('403', response=Mock()), 'Failed to download', 'Access denied'),
    (HfHubHTTPError('500', response=Mock()), 'Failed to download', '500'),
    (OSError('offline'), 'Failed to download', 'Troubleshooting'),
])
def test_download_errors_report_and_restore_credentials(download_services, monkeypatch, error, message, hint):
    download, _ = download_services
    download.side_effect = error
    monkeypatch.setenv('HF_TOKEN', 'saved')
    console = Mock()
    with pytest.raises(RuntimeError, match=message) as caught:
        _download_model_with_progress('base', console)
    assert caught.value.__cause__ is error
    assert any(hint in str(c) for c in console.print.call_args_list)
    import os
    assert os.environ['HF_TOKEN'] == 'saved'
