"""Local source runs must not share installed runtime state."""

from pathlib import Path

from dictare.hotkey.runtime_status import get_runtime_status_path
from dictare.utils.paths import get_data_dir, get_dictare_dir, get_pid_path


def test_default_paths_are_unchanged(monkeypatch):
    monkeypatch.delenv("DICTARE_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("DICTARE_DATA_DIR", raising=False)
    assert get_dictare_dir() == Path.home() / ".dictare"
    assert get_data_dir() == Path.home() / ".local/share/dictare"


def test_source_state_uses_separate_runtime_and_data(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    data = tmp_path / "data"
    monkeypatch.setenv("DICTARE_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("DICTARE_DATA_DIR", str(data))
    assert get_pid_path() == runtime / "engine.pid"
    assert get_runtime_status_path() == runtime / "hotkey_runtime_status"
    assert get_data_dir() == data
