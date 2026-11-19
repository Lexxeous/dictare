"""Permission status behavior without touching system permissions."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dictare.platform import permissions as p


def test_permission_cache_expires(monkeypatch):
    monkeypatch.setattr(p.sys, "platform", "darwin")
    monkeypatch.setattr(p, "_cache", None)
    monkeypatch.setattr(p, "_cache_time", 0)
    clock = iter([10, 12, 16])
    monkeypatch.setattr(p.time, "monotonic", lambda: next(clock))
    check = MagicMock(side_effect=[{"microphone": False}, {"microphone": True}])
    monkeypatch.setattr(p, "_check_via_launcher", check)
    assert p.get_permissions() == {"microphone": False}
    assert p.get_permissions() == {"microphone": False}
    assert p.get_permissions() == {"microphone": True}
    assert check.call_count == 2


@pytest.mark.parametrize("name,key", [("is_accessibility_granted", "accessibility"), ("is_microphone_granted", "microphone"), ("is_input_monitoring_granted", "input_monitoring")])
def test_permission_accessors(monkeypatch, name, key):
    monkeypatch.setattr(p, "get_permissions", lambda: {key: False})
    assert getattr(p, name)() is False


@pytest.mark.parametrize("name,url", [("open_accessibility_settings", p.ACCESSIBILITY_SETTINGS_URL), ("open_microphone_settings", p.MICROPHONE_SETTINGS_URL), ("open_input_monitoring_settings", p.INPUT_MONITORING_SETTINGS_URL)])
def test_open_settings_only_on_mac(monkeypatch, name, url):
    run = MagicMock()
    monkeypatch.setattr(p.subprocess, "Popen", run)
    monkeypatch.setattr(p.sys, "platform", "linux")
    getattr(p, name)()
    run.assert_not_called()
    monkeypatch.setattr(p.sys, "platform", "darwin")
    getattr(p, name)()
    run.assert_called_once_with(["open", url])


def test_installed_launcher_takes_priority(monkeypatch, tmp_path):
    launcher = tmp_path / "Dictare"
    launcher.touch()
    monkeypatch.delenv("DICTARE_DEV_NATIVE", raising=False)
    monkeypatch.setattr("dictare.daemon.app_bundle.get_executable_path", lambda: str(launcher))
    assert p._find_launcher() == str(launcher)


@pytest.mark.parametrize("content,expected", [("active", True), ("confirmed", True), ("failed", False), (None, True)])
def test_input_monitoring_status(monkeypatch, tmp_path, content, expected):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    state_dir = tmp_path / ".dictare"
    state_dir.mkdir()
    if content is not None:
        (state_dir / "hotkey_status").write_text(content)
    assert p._check_input_monitoring() is expected


@pytest.mark.parametrize("content,expected", [(" Granted ", True), ("missing", False), ("other", None), (None, None)])
def test_accessibility_status(monkeypatch, tmp_path, content, expected):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    state_dir = tmp_path / ".dictare"
    state_dir.mkdir()
    if content is not None:
        (state_dir / "accessibility_status").write_text(content)
    assert p._check_accessibility_runtime() is expected


@pytest.mark.parametrize("launcher_ax,runtime_ax,expected", [(True, False, True), (False, True, True), (False, False, False)])
def test_launcher_permissions_merge_runtime(monkeypatch, launcher_ax, runtime_ax, expected):
    monkeypatch.setattr(p, "_find_launcher", lambda: "/test/launcher")
    monkeypatch.setattr(p, "_check_accessibility_runtime", lambda: runtime_ax)
    monkeypatch.setattr(p, "_check_input_monitoring", lambda: False)
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps({"accessibility": launcher_ax, "microphone": False})))
    assert p._check_via_launcher() == {"accessibility": expected, "microphone": False, "input_monitoring": False}


@pytest.mark.parametrize("failure", [OSError("missing"), subprocess.TimeoutExpired("launcher", 5), ValueError("bad")])
def test_launcher_permission_fallback(monkeypatch, failure):
    monkeypatch.setattr(p, "_find_launcher", lambda: "/test/launcher")
    if isinstance(failure, ValueError):
        run = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="bad json"))
    else:
        run = MagicMock(side_effect=failure)
    monkeypatch.setattr(p.subprocess, "run", run)
    monkeypatch.setattr(p, "_check_fallback", lambda: {"fallback": True})
    assert p._check_via_launcher() == {"fallback": True}


def test_mic_launcher_and_fallback(monkeypatch):
    monkeypatch.setattr(p, "_find_launcher", lambda: "/test/launcher")
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{"microphone": false}'))
    assert p._check_mic_via_launcher() is False
    monkeypatch.setattr(p, "_find_launcher", lambda: None)
    monkeypatch.setattr(p, "_check_mic_fallback", lambda: True)
    assert p._check_mic_via_launcher() is True


def test_find_launcher_uses_brew_hint_after_installed_candidates(monkeypatch, tmp_path):
    from pathlib import Path

    from dictare.daemon import app_bundle

    monkeypatch.delenv("DICTARE_DEV_NATIVE", raising=False)
    monkeypatch.delenv("DICTARE_HOMEBREW_BUNDLE", raising=False)
    monkeypatch.setattr(app_bundle, "get_executable_path", lambda: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    bundle = tmp_path / "Cellar" / "Dictare.app"
    executable = bundle / "Contents" / "MacOS" / "Dictare"
    executable.parent.mkdir(parents=True)
    executable.touch()
    hint = tmp_path / ".dictare" / "homebrew_bundle_path"
    hint.parent.mkdir()
    hint.write_text(str(bundle))
    assert p._find_launcher() == str(executable)


def test_find_launcher_uses_environment_bundle_when_hint_missing(monkeypatch, tmp_path):
    from pathlib import Path

    from dictare.daemon import app_bundle

    monkeypatch.delenv("DICTARE_DEV_NATIVE", raising=False)
    monkeypatch.setenv("DICTARE_HOMEBREW_BUNDLE", str(tmp_path))
    monkeypatch.setattr(app_bundle, "get_executable_path", lambda: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    executable = tmp_path / "Contents" / "MacOS" / "Dictare"
    executable.parent.mkdir(parents=True)
    executable.touch()
    assert p._find_launcher() == str(executable)


@pytest.mark.parametrize("status, expected", [(3, True), (2, False)])
def test_microphone_fallback_reads_avfoundation_authorization(monkeypatch, status, expected):
    import sys
    from types import SimpleNamespace

    monkeypatch.setattr(p.ctypes.cdll, "LoadLibrary", lambda path: None)
    device = SimpleNamespace(authorizationStatusForMediaType_=lambda media: status)
    monkeypatch.setitem(sys.modules, "objc", SimpleNamespace(lookUpClass=lambda name: device))
    assert p._check_mic_fallback() is expected
