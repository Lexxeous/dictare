"""Download progress behavior without network access."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import huggingface_hub
import pytest
from rich.console import Console

from dictare.utils import hf_download as hf


def test_cache_directory_size_and_missing_path(monkeypatch, tmp_path):
    monkeypatch.setattr(hf.Path, "home", lambda: tmp_path)
    path = hf.get_hf_cache_dir("owner/model")
    assert path == tmp_path / ".cache/huggingface/hub/models--owner--model"
    assert hf.get_cache_size("owner/model") == 0
    path.mkdir(parents=True)
    (path / "weights").write_bytes(b"12345")
    (path / "config").write_bytes(b"12")
    assert hf.get_cache_size("owner/model") == 7


def test_repo_size_and_cached_check_handle_hub_failures(monkeypatch):
    tree = Mock(return_value=[SimpleNamespace(size=4), SimpleNamespace(size=6), SimpleNamespace()])
    monkeypatch.setattr(huggingface_hub, "list_repo_tree", tree)
    assert hf.get_repo_size("org/model") == 10
    tree.assert_called_with("org/model", repo_type="model")
    tree.side_effect = OSError("offline")
    assert hf.get_repo_size("org/model") is None
    cache = Mock(return_value="/cache/config.json")
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", cache)
    assert hf.is_repo_cached("org/model")
    cache.side_effect = OSError("unavailable")
    assert not hf.is_repo_cached("org/model")


def test_monitor_reports_size_and_stops(monkeypatch):
    progress = Mock()
    monitor = hf.DownloadProgressMonitor("repo", 100, progress, "task")
    monkeypatch.setattr(hf, "get_cache_size", lambda repo: 23)
    monkeypatch.setattr(hf.time, "sleep", lambda interval: monitor._stop.set())
    monitor._monitor()
    progress.update.assert_called_once_with("task", completed=23)
    monitor.stop()


@pytest.mark.parametrize("expected_size", [None, 123])
def test_uncached_download_reports_completion(monkeypatch, expected_size):
    monkeypatch.setattr(hf, "is_repo_cached", lambda repo: False)
    monkeypatch.setattr(hf, "get_repo_size", lambda repo: expected_size)
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    assert hf.download_with_progress("org/model", lambda: "loaded", fallback_size_gb=0.001, console=console) == "loaded"
    assert "Model ready" in output.getvalue()


def test_cached_download_skips_size_lookup(monkeypatch):
    monkeypatch.setattr(hf, "is_repo_cached", lambda repo: True)
    size = Mock()
    monkeypatch.setattr(hf, "get_repo_size", size)
    assert hf.download_with_progress("repo", lambda: "model", console=Mock()) == "model"
    size.assert_not_called()
