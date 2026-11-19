"""Model management behavior using isolated cache and download doubles."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from dictare.cli import models
from dictare.utils import hf_download


@pytest.fixture
def registry(monkeypatch):
    data = {
        'whisper-small': {'type': 'stt', 'repo': 'org/stt', 'size_gb': 1, 'description': 'STT'},
        'tts-model': {'type': 'tts', 'repo': 'org/tts', 'size_gb': 2, 'description': 'TTS', 'venv': 'engine'},
        'builtin': {'type': 'tts', 'builtin': True},
    }
    monkeypatch.setattr(models, '_MODEL_REGISTRY', data)
    return data


def test_configured_models_maps_whisper_and_venv(registry):
    config = SimpleNamespace(stt=SimpleNamespace(model='small'), tts=SimpleNamespace(engine='engine'))
    assert models._get_configured_models(config) == {'whisper-small': 'stt', 'tts-model': 'tts'}


@pytest.mark.parametrize('size,expected', [(1, '1 B'), (1024, '1.0 KB'), (1048576, '1.0 MB'), (1073741824, '1.0 GB')])
def test_format_sizes(size, expected):
    assert models._format_size(size) == expected


def test_ensure_models_downloads_missing_and_propagates_failure(monkeypatch, registry):
    config = SimpleNamespace(stt=SimpleNamespace(model='small'), tts=SimpleNamespace(engine='engine'))
    monkeypatch.setattr(hf_download, 'is_repo_cached', lambda repo, check: repo == 'org/stt')
    download = Mock()
    monkeypatch.setattr(hf_download, 'download_with_progress', download)
    assert models.ensure_required_models(config)
    assert download.call_args.args[0] == 'org/tts'
    download.side_effect = RuntimeError('offline')
    assert not models.ensure_required_models(config)


def test_list_displays_cached_missing_and_unconfigured(monkeypatch, registry):
    config = SimpleNamespace(stt=SimpleNamespace(model='small'), tts=SimpleNamespace(engine='engine'))
    monkeypatch.setattr(hf_download, 'is_repo_cached', lambda repo, check: repo == 'org/stt')
    monkeypatch.setattr(hf_download, 'get_cache_size', lambda repo: 1024)
    output = Mock()
    monkeypatch.setattr(models.console, 'print', output)
    models._show_models_list(config)
    table = output.call_args.args[0]
    assert table.row_count == 2
    assert 'MISSING' in str(table.columns[3]._cells[1])


def test_pull_checks_cache_and_handles_failures(monkeypatch, registry):
    runner = CliRunner()
    assert runner.invoke(models.app, ['pull', 'missing']).exit_code == 1
    assert runner.invoke(models.app, ['pull', 'builtin']).exit_code == 0
    monkeypatch.setattr(hf_download, 'is_repo_cached', lambda *a: True)
    assert 'already cached' in runner.invoke(models.app, ['pull', 'whisper-small']).output
    monkeypatch.setattr(hf_download, 'is_repo_cached', lambda *a: False)
    download = Mock()
    monkeypatch.setattr(hf_download, 'download_with_progress', download)
    assert runner.invoke(models.app, ['pull', 'whisper-small']).exit_code == 0
    download.side_effect = RuntimeError('offline')
    assert runner.invoke(models.app, ['pull', 'whisper-small']).exit_code == 1


def test_remove_uses_isolated_cache(monkeypatch, registry, tmp_path):
    runner = CliRunner()
    monkeypatch.setattr(hf_download, 'get_hf_cache_dir', lambda repo: tmp_path / repo.replace('/', '-'))
    path = tmp_path / 'org-stt'
    path.mkdir()
    assert runner.invoke(models.app, ['rm', 'whisper-small']).exit_code == 0
    assert not path.exists()
    assert runner.invoke(models.app, ['rm', 'whisper-small']).exit_code == 0
    assert runner.invoke(models.app, ['rm', 'unknown']).exit_code == 1
    assert runner.invoke(models.app, ['rm', 'builtin']).exit_code == 0
    (tmp_path / 'org-stt').mkdir()
    (tmp_path / 'org-tts').mkdir()
    assert runner.invoke(models.app, ['rm', 'all'], input='y\n').exit_code == 0
    assert list(tmp_path.iterdir()) == []
