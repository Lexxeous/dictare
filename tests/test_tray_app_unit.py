"""Behavioral tests for tray state and controls without a desktop session."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.tray import app as tray


@pytest.fixture
def instance(monkeypatch):
    monkeypatch.setattr(tray.TrayApp, "_load_output_mode", lambda self: None)
    return tray.TrayApp()


def test_state_targets_and_icons(instance, monkeypatch):
    icon = SimpleNamespace(icon=None, title=None, menu=None)
    instance._icon = icon
    monkeypatch.setattr(tray, "_run_on_main_thread", lambda fn: fn())
    monkeypatch.setattr(tray, "_load_icon", lambda name: name)
    monkeypatch.setattr(instance, "_create_menu", lambda: "menu")
    instance.set_state("loading", 25, "STT")
    assert (icon.icon, icon.title, icon.menu) == ("dictare_loading", "Dictare — Loading STT…", "menu")
    instance._microphone_granted = False
    instance.set_state("listening")
    assert icon.icon == "dictare_disconnected"
    assert icon.title == "Dictare — Listening"
    instance.set_state("invalid")
    assert instance._state == "listening"
    instance.set_targets(["one", "two"])
    assert instance._current_target == "one"
    instance.set_targets(["one", "two"], current="two")
    assert instance._current_target == "two"
    instance.set_targets([])
    assert instance._current_target == ""


def test_callbacks_and_persistence_failure(instance, monkeypatch):
    import dictare.config
    callback = Mock()
    instance.on_target_change(callback)
    instance.on_output_mode_change(callback)
    instance.on_toggle_listening(callback)
    monkeypatch.setattr(dictare.config, "set_config_value", Mock(side_effect=OSError("read only")))
    instance._make_target_handler("shell")(None, None)
    instance._make_output_mode_handler("agents")(None, None)
    instance._on_toggle_listening(None, None)
    assert callback.call_args_list == [(("shell",),), (("agents",),), ((),)]
    assert instance.get_output_mode() == "agents"
    instance.set_output_mode("keyboard")
    assert instance.get_output_mode() == "keyboard"


def test_menu_reflects_permissions_and_target(instance, monkeypatch):
    class Item:
        def __init__(self, label, action, **options):
            self.label, self.action, self.options = label, action, options
    class Menu(tuple):
        SEPARATOR = object()
        def __new__(cls, *items):
            return super().__new__(cls, items)
    monkeypatch.setitem(sys.modules, "pystray", SimpleNamespace(Menu=Menu, MenuItem=Item))
    monkeypatch.setattr(tray.sys, "platform", "darwin")
    monkeypatch.setattr(tray, "_native_launcher_running", lambda *args: True)
    instance._state = "listening"
    instance._input_monitoring_granted = False
    instance._output_mode = "agents"
    instance._targets = ["shell"]
    instance._current_target = "shell"
    menu = instance._create_menu()
    labels = [item.label for item in menu if isinstance(item, Item)]
    assert "Status: LISTENING" in labels
    assert "⚠ Grant Input Monitoring" in labels
    assert "Stop Listening" in labels
    assert "Current: shell" in labels
    assert "Open Dictare App" in labels


def test_settings_choose_browser_or_editor(instance, monkeypatch):
    import webbrowser

    import dictare.config
    monkeypatch.setattr(dictare.config, "load_config", lambda: SimpleNamespace(server=SimpleNamespace(host="localhost", port=123)))
    browser = Mock()
    editor = Mock()
    monkeypatch.setattr(webbrowser, "open", browser)
    monkeypatch.setattr(instance, "_open_config_in_editor", editor)
    instance._on_open_settings(None, None)
    editor.assert_called_once()
    instance._state = "off"
    instance._on_open_settings(None, None)
    browser.assert_called_once_with("http://localhost:123/settings")


def test_service_actions_use_backend_or_http(instance, monkeypatch):
    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(tray.threading, "Thread", ImmediateThread)
    backend = SimpleNamespace(is_loaded=Mock(return_value=True), stop=Mock(), start=Mock())
    monkeypatch.setattr(instance, "_get_service_backend", lambda: backend)
    shutdown = Mock()
    monkeypatch.setattr(instance, "_shutdown_engine_http", shutdown)
    instance._on_stop_service(None, None)
    instance._on_start_service(None, None)
    backend.stop.assert_called_once()
    backend.start.assert_called_once()
    backend.is_loaded.return_value = False
    instance._on_stop_service(None, None)
    shutdown.assert_called_once()


def test_loopback_and_icon_fallback(monkeypatch, tmp_path):
    assert tray._native_loopback_host("0.0.0.0") == "127.0.0.1"
    assert tray._native_loopback_host("::") == "::1"
    assert tray._native_loopback_host("example.com") is None
    monkeypatch.setattr(tray, "ICONS_DIR", tmp_path)
    assert tray._load_icon("missing").size == (22, 22)


def test_shutdown_engine_sends_control_and_ignores_connection_error(instance, monkeypatch):
    import openvip

    import dictare.config

    monkeypatch.setattr(dictare.config, "load_config", lambda: SimpleNamespace(server=SimpleNamespace(host="localhost", port=42)))
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr(openvip, "Client", factory)
    instance._shutdown_engine_http()
    factory.assert_called_once_with("http://localhost:42/openvip", timeout=2.0)
    client.control.assert_called_once_with("engine.shutdown")
    client.control.side_effect = OSError("offline")
    instance._shutdown_engine_http()


def test_open_config_editor_creates_missing_config(instance, monkeypatch, tmp_path):
    import subprocess

    import dictare.config

    path = tmp_path / "config.toml"
    create = Mock(return_value=path)
    popen = Mock()
    monkeypatch.setattr(dictare.config, "get_config_path", lambda: path)
    monkeypatch.setattr(dictare.config, "create_default_config", create)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(tray.sys, "platform", "linux")
    monkeypatch.setenv("EDITOR", "my-editor")
    instance._open_config_in_editor()
    create.assert_called_once_with()
    popen.assert_called_once_with(["my-editor", str(path)])


def test_native_window_open_requires_local_address(instance, monkeypatch):
    import dictare.config

    server = SimpleNamespace(host="0.0.0.0", port=4321)
    center = Mock()
    monkeypatch.setitem(sys.modules, "Foundation", SimpleNamespace(NSDistributedNotificationCenter=SimpleNamespace(defaultCenter=lambda: center)))
    monkeypatch.setattr(dictare.config, "load_config", lambda: SimpleNamespace(server=server))
    monkeypatch.setenv("DICTARE_NATIVE_BUNDLE_ID", "example.app")
    instance._on_open_app(None, None)
    center.postNotificationName_object_userInfo_deliverImmediately_.assert_called_once_with(
        "example.app.open-window", None, {"host": "127.0.0.1", "port": 4321}, True
    )
    server.host = "remote.example"
    instance._on_open_app(None, None)
    assert center.postNotificationName_object_userInfo_deliverImmediately_.call_count == 1


def test_about_dialog_dispatch_and_macos_fallback(instance, monkeypatch):
    monkeypatch.setattr(tray, "_load_credits", lambda: [{"title": "Sound"}])
    macos, tk = Mock(), Mock()
    monkeypatch.setattr(instance, "_show_about_dialog_macos", macos)
    monkeypatch.setattr(instance, "_show_about_dialog_tk", tk)
    monkeypatch.setattr(tray.sys, "platform", "darwin")
    instance._show_about_dialog()
    assert macos.call_args.args[1] == [{"title": "Sound"}]
    monkeypatch.setattr(tray.sys, "platform", "linux")
    instance._show_about_dialog()
    assert tk.call_args.args[1] == [{"title": "Sound"}]


def test_tk_about_dialog_renders_credits_and_centers(instance, monkeypatch):
    root = Mock()
    root.winfo_width.return_value = 200
    root.winfo_height.return_value = 100
    root.winfo_screenwidth.return_value = 1000
    root.winfo_screenheight.return_value = 700
    widgets = []

    def widget(*args, **kwargs):
        result = Mock()
        widgets.append((kwargs, result))
        return result

    tk = SimpleNamespace(Tk=lambda: root, PhotoImage=Mock(return_value='icon'),
                         ttk=SimpleNamespace(Frame=widget, Label=widget, Separator=widget, Button=widget))
    monkeypatch.setitem(sys.modules, 'tkinter', tk)
    instance._show_about_dialog_tk('1.2', [{'title': 'Bell', 'author': 'A', 'source': 'B'}])
    labels = [data.get('text') for data, _ in widgets]
    assert 'Version 1.2' in labels
    assert 'Bell — A (B)' in labels
    root.geometry.assert_called_once_with('+400+200')
    root.mainloop.assert_called_once()


def test_macos_about_dialog_renders_credits(instance, monkeypatch):
    application, alert = Mock(), Mock()
    appkit = SimpleNamespace(NSApplication=SimpleNamespace(sharedApplication=lambda: application),
                             NSAlert=SimpleNamespace(alloc=lambda: SimpleNamespace(init=lambda: alert)),
                             NSImage=Mock())
    monkeypatch.setitem(sys.modules, 'AppKit', appkit)
    monkeypatch.setattr(tray, '_run_on_main_thread', lambda f: f())
    instance._show_about_dialog_macos('3', [{'title': 'Chime', 'author': 'A', 'source': 'B'}])
    alert.setMessageText_.assert_called_once_with('Dictare 3')
    assert 'Chime — A (B)' in alert.setInformativeText_.call_args.args[0]
    alert.runModal.assert_called_once()


def test_macos_about_dialog_falls_back(instance, monkeypatch):
    monkeypatch.setitem(sys.modules, 'AppKit', None)
    fallback = Mock()
    monkeypatch.setattr(instance, '_show_about_dialog_tk', fallback)
    instance._show_about_dialog_macos('3', [])
    fallback.assert_called_once_with('3', [])


def test_polling_updates_status_and_permissions(instance, monkeypatch):
    import openvip

    import dictare.status

    status = SimpleNamespace(platform={"output": {"available_agents": ["shell"], "current_agent": "shell", "mode": "agents"}, "permissions": {"microphone": False, "input_monitoring": False}})
    client = Mock()
    client.get_status.return_value = status
    factory = Mock(return_value=client)
    monkeypatch.setattr(openvip, "Client", factory)
    monkeypatch.setattr(dictare.status, "resolve_display_state", lambda _: ("recording", None))
    monkeypatch.setattr(instance, "_update_menu", Mock())
    monkeypatch.setattr(instance, "_update_icon", Mock())
    instance._poll_stop.wait = Mock(return_value=True)
    instance.start_status_streaming(host="localhost", port=9876)
    instance._poll_thread.join(timeout=2)
    assert not instance._poll_thread.is_alive()
    factory.assert_called_once_with("http://localhost:9876/openvip", timeout=2.0)
    assert instance._state == "listening"
    assert instance._current_target == "shell"
    assert instance._output_mode == "agents"
    assert not instance._microphone_granted
    assert not instance._input_monitoring_granted
    instance.stop_status_polling()
    assert not instance._polling
    assert instance._poll_stop.is_set()


def test_polling_marks_unreachable_engine_disconnected(instance, monkeypatch):
    import openvip

    monkeypatch.setattr(openvip, "Client", Mock(return_value=SimpleNamespace(get_status=Mock(side_effect=OSError("offline")))))
    instance._poll_stop.wait = Mock(return_value=True)
    instance._state = "listening"
    instance.start_status_streaming()
    instance._poll_thread.join(timeout=2)
    assert instance._state == "disconnected"
    instance.stop_status_polling()


def test_main_registers_controls_and_cleans_up(monkeypatch):
    import signal

    import openvip

    import dictare.config
    import dictare.logging.setup
    import dictare.tray.lifecycle

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target
        def start(self):
            self.target()

    config = SimpleNamespace(server=SimpleNamespace(host="localhost", port=1234), output=SimpleNamespace(mode="agents"))
    client = Mock()
    app = Mock()
    app._icon = Mock()
    signals = {}
    monkeypatch.setitem(sys.modules, "pystray", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=object()))
    monkeypatch.setattr(dictare.config, "load_config", lambda: config)
    monkeypatch.setattr(dictare.logging.setup, "get_default_log_path", lambda _: "log")
    monkeypatch.setattr(dictare.logging.setup, "setup_logging", Mock())
    write_pid = Mock()
    remove_pid = Mock()
    monkeypatch.setattr(dictare.tray.lifecycle, "write_pid", write_pid)
    monkeypatch.setattr(dictare.tray.lifecycle, "remove_pid", remove_pid)
    monkeypatch.setattr(openvip, "Client", lambda *a, **kw: client)
    monkeypatch.setattr(tray, "TrayApp", lambda: app)
    monkeypatch.setattr(tray, "_hide_dock_icon", Mock())
    monkeypatch.setattr(tray.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(signal, "signal", lambda sig, handler: signals.update({sig: handler}))
    tray.main()
    app.on_toggle_listening.call_args.args[0]()
    app.on_output_mode_change.call_args.args[0]("keyboard")
    app.on_target_change.call_args.args[0]("terminal")
    assert [call.args[0] for call in client.control.call_args_list] == ["stt.toggle", "output.set_mode:keyboard", "output.set_agent:terminal"]
    app.start_status_streaming.assert_called_once_with(host="localhost", port=1234)
    signals[signal.SIGTERM](signal.SIGTERM, None)
    app._icon.stop.assert_called_once()
    write_pid.assert_called_once()
    remove_pid.assert_called_once()


def test_service_actions_use_platform_backend(instance, monkeypatch):
    import threading

    from dictare.daemon import systemd

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    monkeypatch.setattr(sys, "platform", "linux")
    start = Mock()
    stop = Mock()
    monkeypatch.setattr(systemd, "start", start)
    monkeypatch.setattr(systemd, "stop", stop)
    monkeypatch.setattr(systemd, "is_loaded", lambda: True)
    instance._on_restart_engine(None, None)
    instance._on_stop_service(None, None)
    instance._on_start_service(None, None)
    assert start.call_count == 2
    assert stop.call_count == 2


def test_service_stop_falls_back_to_http(instance, monkeypatch):
    import threading

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    monkeypatch.setattr(instance, "_get_service_backend", lambda: None)
    shutdown = Mock()
    monkeypatch.setattr(instance, "_shutdown_engine_http", shutdown)
    instance._on_stop_service(None, None)
    shutdown.assert_called_once_with()


def test_service_backend_errors_do_not_escape_tray_callback(instance, monkeypatch, caplog):
    import threading

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    backend = SimpleNamespace(start=Mock(side_effect=OSError("service unavailable")))
    monkeypatch.setattr(instance, "_get_service_backend", lambda: backend)
    instance._on_start_service(None, None)
    assert "service unavailable" in caplog.text


def test_macos_launcher_and_dock_controls(monkeypatch):
    application = Mock()
    running = Mock(return_value=[object()])
    appkit = SimpleNamespace(
        NSApplication=SimpleNamespace(sharedApplication=lambda: application),
        NSRunningApplication=SimpleNamespace(runningApplicationsWithBundleIdentifier_=running),
    )
    monkeypatch.setitem(sys.modules, 'AppKit', appkit)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    tray._hide_dock_icon()
    assert tray._native_launcher_running('test.bundle')
    application.setActivationPolicy_.assert_called_once_with(1)
    running.assert_called_once_with('test.bundle')


def test_run_on_main_thread_dispatches_background_calls(monkeypatch):
    import threading
    scheduled = Mock()
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(threading, 'current_thread', lambda: object())
    monkeypatch.setitem(sys.modules, 'PyObjCTools.AppHelper', SimpleNamespace(callAfter=scheduled))
    callback = Mock()
    tray._run_on_main_thread(callback)
    scheduled.assert_called_once_with(callback)
    callback.assert_not_called()


def test_quit_terminates_native_development_launcher(instance, monkeypatch):
    native = Mock()
    applications = Mock(return_value=[native])
    monkeypatch.setenv('DICTARE_DEV_NATIVE', '1')
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setitem(sys.modules, 'AppKit', SimpleNamespace(NSRunningApplication=SimpleNamespace(runningApplicationsWithBundleIdentifier_=applications)))
    instance._icon = Mock()
    instance._on_quit(None, None)
    native.terminate.assert_called_once_with()
    instance._icon.stop.assert_called_once_with()
