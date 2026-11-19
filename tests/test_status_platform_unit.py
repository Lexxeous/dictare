"""Status report behavior for platform permissions and hotkey health."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.core import status_report
from dictare.hotkey import runtime_status
from dictare.platform import permissions as platform_permissions
from dictare.utils import paths


def test_audio_devices_handles_backend_error(monkeypatch):
    from dictare.audio.capture import AudioCapture

    monkeypatch.setattr(AudioCapture, "list_devices", Mock(side_effect=OSError("no device")))
    assert status_report.audio_devices() == {"input": [], "output": [], "default_input": None, "default_output": None}


@pytest.mark.parametrize("runtime,expected_active,expected_status", [
    ({"capture_healthy": True, "status": "active"}, True, "confirmed"),
    ({"capture_healthy": False, "status": "unavailable"}, False, "unavailable"),
])
def test_macos_hotkey_uses_runtime_health(monkeypatch, runtime, expected_active, expected_status):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(runtime_status, "read_runtime_status", lambda: runtime)
    engine = SimpleNamespace(_hotkey=None, _hotkey_pre_confirmed=True)
    assert status_report.hotkey_active(engine) is expected_active
    assert status_report.hotkey_status_raw(engine) == expected_status


def test_macos_hotkey_falls_back_to_launcher_file(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(runtime_status, "read_runtime_status", lambda: None)
    monkeypatch.setattr(paths, "get_dictare_dir", lambda: tmp_path)
    engine = SimpleNamespace(_hotkey=None, _hotkey_pre_confirmed=False)
    assert not status_report.hotkey_active(engine)
    assert status_report.hotkey_status_raw(engine) == "unknown"
    (tmp_path / "hotkey_status").write_text("confirmed\n")
    assert status_report.hotkey_active(engine)
    assert status_report.hotkey_status_raw(engine) == "confirmed"


def test_macos_permissions_include_settings_urls(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(platform_permissions, "get_permissions", lambda: {"microphone": False, "accessibility": True})
    result = status_report.permissions()
    assert result["microphone"] is False
    assert result["accessibility"] is True
    assert result["microphone_url"] == platform_permissions.MICROPHONE_SETTINGS_URL
    assert result["accessibility_url"] == platform_permissions.ACCESSIBILITY_SETTINGS_URL
