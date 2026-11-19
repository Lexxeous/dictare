"""Uninstall service handling uses temporary files and never invokes system tools."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from typer import Typer
from typer.testing import CliRunner

from dictare.cli import uninstall


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_service_files_moved_and_commands_requested(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(uninstall.sys, "platform", platform)
    run = Mock()
    monkeypatch.setattr(uninstall, "_run_best_effort", run)
    if platform == "darwin":
        service = tmp_path / "Library/LaunchAgents/dev.dragfly.dictare.plist"
        app = tmp_path / "Applications/Dictare.app"
        app.mkdir(parents=True)
    else:
        service = tmp_path / ".config/systemd/user/dictare.service"
    service.parent.mkdir(parents=True, exist_ok=True)
    service.write_text("service")
    trash = tmp_path / "trash"
    uninstall._stop_and_move_services(trash)
    assert not service.exists()
    assert (trash / service.name).read_text() == "service"
    if platform == "darwin":
        assert (trash / "Dictare.app").is_dir()
        assert run.call_count == 5
    else:
        assert run.call_count == 3
        run.assert_any_call(["systemctl", "--user", "daemon-reload"])


def test_runtime_moves_selected_data_to_trash(tmp_path, monkeypatch):
    from dictare import runtime_store

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(uninstall, "_stop_and_move_services", lambda _: None)
    monkeypatch.setattr(uninstall, "_trash_root", lambda: tmp_path / "trash")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(runtime_store, "RUNTIME_ROOT", runtime)
    for name in ("BIN_DIR", "CURRENT_LINK", "PREVIOUS_LINK", "VERSIONS_DIR", "LOCK_DIR", "SHIM_PATH"):
        monkeypatch.setattr(runtime_store, name, runtime / name)
    (runtime / "SHIM_PATH").write_text("shim")
    config = tmp_path / ".config/dictare"
    config.mkdir(parents=True)
    (config / "settings.toml").write_text("config")
    trash = uninstall.uninstall_runtime(wipe_config=True)
    assert (trash / "SHIM_PATH").read_text() == "shim"
    assert (trash / "dictare/settings.toml").read_text() == "config"
    assert not config.exists()


def test_uninstall_command_reports_failure(monkeypatch):
    app = Typer()
    uninstall.register(app)
    def fail(**kwargs):
        raise RuntimeError("cannot move")
    monkeypatch.setattr(uninstall, "uninstall_runtime", fail)
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 1
    assert "cannot move" in result.output
