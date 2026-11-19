"""LaunchAgent installation and permission onboarding without system changes."""

from unittest.mock import Mock, call

from dictare.daemon import app_bundle, launchd


def test_install_replaces_loaded_service_and_installs_tray(tmp_path, monkeypatch):
    plist = tmp_path / "agents" / "dictare.plist"
    monkeypatch.setattr(launchd, "get_plist_path", lambda: plist)
    monkeypatch.setattr(app_bundle, "sync_service_python_path", lambda executable: "/python")
    create = Mock()
    monkeypatch.setattr(app_bundle, "create_app_bundle", create)
    monkeypatch.setattr(launchd, "generate_plist", lambda executable: f"plist for {executable}")
    permission = Mock()
    stop = Mock()
    kill = Mock()
    tray = Mock()
    run = Mock()
    monkeypatch.setattr(launchd, "_request_input_monitoring", permission)
    monkeypatch.setattr(launchd, "is_loaded", lambda: True)
    monkeypatch.setattr(launchd, "_stop_service", stop)
    monkeypatch.setattr(launchd, "_kill_orphan_processes", kill)
    monkeypatch.setattr(launchd, "install_tray", tray)
    monkeypatch.setattr(launchd.subprocess, "run", run)
    launcher = tmp_path / "binary"
    launchd.install(prebuilt_launcher=launcher)
    create.assert_called_once_with("/python", prebuilt_launcher=launcher)
    permission.assert_called_once()
    stop.assert_called_once()
    kill.assert_called_once()
    run.assert_called_once_with(["launchctl", "load", str(plist)], check=True)
    tray.assert_called_once()
    assert plist.read_text() == "plist for /python"


def test_uninstall_removes_agent_after_stopping(tmp_path, monkeypatch):
    plist = tmp_path / "agent.plist"
    plist.write_text("agent")
    monkeypatch.setattr(launchd, "get_plist_path", lambda: plist)
    monkeypatch.setattr(launchd, "is_loaded", lambda: True)
    stop, tray, remove = Mock(), Mock(), Mock()
    monkeypatch.setattr(launchd, "_stop_service", stop)
    monkeypatch.setattr(launchd, "uninstall_tray", tray)
    monkeypatch.setattr(app_bundle, "remove_app_bundle", remove)
    launchd.uninstall()
    stop.assert_called_once()
    tray.assert_called_once()
    remove.assert_called_once()
    assert not plist.exists()


def test_input_monitoring_prompts_once_per_launcher_hash(tmp_path, monkeypatch, capsys):
    app = tmp_path / "Dictare.app"
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (macos / "launcher_hash").write_text("abc")
    monkeypatch.setattr(app_bundle, "get_app_path", lambda: app)
    monkeypatch.setattr(launchd.Path, "home", lambda: tmp_path)
    run = Mock()
    monkeypatch.setattr(launchd.subprocess, "run", run)
    launchd._request_input_monitoring()
    marker = tmp_path / ".dictare" / "input_monitoring_setup"
    assert marker.read_text() == "abc"
    assert "Input Monitoring" in capsys.readouterr().out
    assert run.call_args_list == [
        call([str(macos / "Dictare"), "--request-input-monitoring"], capture_output=True, text=True),
        call(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"], check=False),
    ]
    run.reset_mock()
    launchd._request_input_monitoring()
    run.assert_not_called()
