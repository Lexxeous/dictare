"""Runtime lifecycle command tests with service and filesystem isolation."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer
from typer.testing import CliRunner

from dictare import runtime_store
from dictare.cli import repair, uninstall, upgrade


@pytest.mark.parametrize("platform,installed,running,no_start,expected", [
    ("linux", False, False, False, ["install", "start"]),
    ("linux", True, True, True, ["stop", "install", "stop"]),
    ("darwin", True, False, False, ["install", "stop"]),
    ("darwin", True, True, False, ["stop", "install"]),
])
def test_repair_preserves_service_state(monkeypatch, platform, installed, running, no_start, expected):
    calls = []
    backend = SimpleNamespace(is_installed=lambda: installed, is_loaded=lambda: running,
                              install=lambda: calls.append("install"), stop=lambda: calls.append("stop"), start=lambda: calls.append("start"))
    monkeypatch.setattr(repair.sys, "platform", platform)
    monkeypatch.setattr(repair, "_get_backend", lambda: backend)
    monkeypatch.setattr(runtime_store, "current_runtime", lambda: Path("runtime"))
    shim, launcher = Mock(), Mock()
    monkeypatch.setattr(runtime_store, "ensure_shim", shim)
    monkeypatch.setattr(runtime_store, "write_launcher_python_path", launcher)
    from dictare.daemon import app_bundle
    migrate = Mock()
    monkeypatch.setattr(app_bundle, "migrate_signed_bundle_from_cellar", migrate)
    repair.repair_runtime(no_start=no_start, force_bundle_migration=True)
    assert calls == expected
    shim.assert_called_once()
    launcher.assert_called_once()
    assert migrate.call_count == (platform == "darwin")


def test_uninstall_moves_files_without_collisions(tmp_path):
    source = tmp_path / "runtime"
    source.write_text("first")
    trash = tmp_path / "trash"
    first = uninstall._move_path(source, trash)
    source.write_text("second")
    second = uninstall._move_path(source, trash)
    assert first.read_text() == "first"
    assert second.name == "runtime.1" and second.read_text() == "second"
    assert uninstall._move_path(source, trash) is None


def test_uninstall_service_commands_are_scoped_to_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(uninstall.sys, "platform", "linux")
    unit = tmp_path / ".config/systemd/user/dictare.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("unit")
    run = Mock()
    monkeypatch.setattr(uninstall, "_run_best_effort", run)
    uninstall._stop_and_move_services(tmp_path / "trash")
    assert (tmp_path / "trash/dictare.service").read_text() == "unit"
    assert [c.args[0][-1] for c in run.call_args_list] == ["dictare.service", "dictare.service", "daemon-reload"]


@pytest.mark.parametrize("filename,expected", [("dictare-1.2-py3-none-any.whl", "1.2"), ("other-1-py3-none-any.whl", None), ("dictare-2.tar.gz", "2"), ("dictare-3.zip", "3"), ("directory", None)])
def test_version_from_path(filename, expected):
    assert upgrade._version_from_path(filename) == expected


def test_upgrade_command_activates_and_repairs(monkeypatch):
    backend = SimpleNamespace(is_installed=lambda: True, is_loaded=lambda: True, stop=Mock())
    monkeypatch.setattr(upgrade, "_get_backend", lambda: backend)
    monkeypatch.setattr(runtime_store, "snapshot", lambda: SimpleNamespace(current_version="1"))
    install, activate, fix = Mock(return_value=Path("/runtime/2")), Mock(), Mock()
    monkeypatch.setattr(runtime_store, "install_runtime", install)
    monkeypatch.setattr(runtime_store, "activate_runtime", activate)
    monkeypatch.setattr(runtime_store, "current_runtime", lambda: Path("/runtime/2"))
    monkeypatch.setattr(repair, "repair_runtime", fix)
    app = typer.Typer()
    upgrade.register(app)
    result = CliRunner().invoke(app, ["upgrade", "--version", "2", "--extras", "a, b,,", "--no-restart"])
    assert result.exit_code == 0, result.output
    install.assert_called_once_with("2", source=None, extras=["a", "b"], reinstall=False)
    backend.stop.assert_called_once()
    activate.assert_called_once_with(Path("/runtime/2"))
    fix.assert_called_once_with(no_start=True)
    assert "runtime active" in result.output


def test_upgrade_and_rollback_failures(monkeypatch):
    app = typer.Typer()
    upgrade.register(app)
    monkeypatch.setattr(upgrade, "_latest_pypi_version", Mock(side_effect=OSError("offline")))
    result = CliRunner().invoke(app, ["upgrade"])
    assert result.exit_code == 1 and "offline" in result.output
    monkeypatch.setattr(upgrade, "_get_backend", lambda: SimpleNamespace(is_installed=lambda: False))
    monkeypatch.setattr(runtime_store, "rollback_runtime", Mock(side_effect=ValueError("no previous runtime")))
    result = CliRunner().invoke(app, ["rollback"])
    assert result.exit_code == 1 and "no previous runtime" in result.output
