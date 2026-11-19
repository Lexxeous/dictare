"""Checks for the native development runner's isolation preflight."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "native_dev", Path(__file__).resolve().parents[1] / "scripts/native_dev.py"
)
native_dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native_dev)


@pytest.fixture
def isolated(monkeypatch):
    def run(args, **kwargs):
        if args[0] == "git":
            return subprocess.CompletedProcess(args, 0, "develop\n", "")
        return subprocess.CompletedProcess(args, 1, "", "")

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, value):
            pass

        def connect_ex(self, address):
            return 1

    monkeypatch.setattr(native_dev.subprocess, "run", run)
    monkeypatch.setattr(native_dev.socket, "socket", Socket)
    monkeypatch.setattr(native_dev, "applications", lambda bundle: [])


def test_preflight_allows_inactive_services(isolated):
    native_dev.preflight(18770)


def test_preflight_rejects_running_installed_app(isolated, monkeypatch):
    monkeypatch.setattr(native_dev, "applications", lambda bundle: [object()] if bundle == "dev.dragfly.dictare" else [])
    with pytest.raises(RuntimeError, match="already running"):
        native_dev.preflight(18770)


def test_preflight_rejects_running_installed_service(isolated, monkeypatch):
    def run(args, **kwargs):
        if args[0] == "git":
            return subprocess.CompletedProcess(args, 0, "develop\n", "")
        return subprocess.CompletedProcess(args, 0, '"PID" = 123;\n', "")

    monkeypatch.setattr(native_dev.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="installed service"):
        native_dev.preflight(18770)


def test_stop_only_terminates_this_checkout(isolated, monkeypatch, tmp_path):
    monkeypatch.setenv("DICTARE_DEV_CHECKOUT", str(tmp_path))

    class App:
        stopped = False

        def bundleURL(self):  # noqa: N802 - AppKit API
            return self

        def path(self):
            return str(tmp_path / ".dictare-dev/Dictare Develop.app")

        def terminate(self):
            self.stopped = True

        def isTerminated(self):  # noqa: N802 - AppKit API
            return self.stopped

    app = App()
    monkeypatch.setattr(native_dev, "applications", lambda bundle: [app])
    native_dev.stop_app()
    assert app.stopped


def test_stop_rejects_another_checkout(isolated, monkeypatch, tmp_path):
    monkeypatch.setenv("DICTARE_DEV_CHECKOUT", str(tmp_path))

    class App:
        def bundleURL(self):  # noqa: N802 - AppKit API
            return self

        def path(self):
            return "/other/Dictare Develop.app"

    monkeypatch.setattr(native_dev, "applications", lambda bundle: [App()])
    with pytest.raises(RuntimeError, match="another checkout"):
        native_dev.stop_app()
