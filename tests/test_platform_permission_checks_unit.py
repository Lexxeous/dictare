"""Exercise permission caching and platform fallbacks without system prompts."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.platform import accessibility, microphone


@pytest.mark.parametrize("module,check_name,public_name", [
    (accessibility, "_check_ax_trusted", "is_accessibility_granted"),
    (microphone, "_check_mic_authorized", "is_microphone_granted"),
])
def test_permission_cache_expires(module, check_name, public_name, monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "darwin")
    clock = Mock(return_value=10.0)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=clock))
    check = Mock(side_effect=[False, True])
    monkeypatch.setattr(module, check_name, check)
    monkeypatch.setattr(module, "_cache_result", None)
    monkeypatch.setattr(module, "_cache_time", 0)
    get = getattr(module, public_name)
    assert get() is False
    clock.return_value = 14
    assert get() is False
    clock.return_value = 16
    assert get() is True
    assert check.call_count == 2


def test_accessibility_request_refreshes_cache(monkeypatch):
    monkeypatch.setattr(accessibility.sys, "platform", "darwin")
    monkeypatch.setattr(accessibility, "_cache_result", None)
    monkeypatch.setattr(accessibility, "_cache_time", 0)
    check = Mock(return_value=True)
    monkeypatch.setattr(accessibility, "_check_ax_trusted", check)
    assert accessibility.request_accessibility() is True
    assert accessibility.is_accessibility_granted() is True
    check.assert_called_once_with(prompt=True)


def test_bundle_check_and_prompt(monkeypatch, tmp_path):
    from dictare.daemon import app_bundle
    executable = tmp_path / "dictare"
    executable.touch()
    monkeypatch.setattr(app_bundle, "get_executable_path", lambda: str(executable))
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout='{"accessibility": false}'))
    launch = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", launch)
    assert accessibility._check_ax_trusted(True) is False
    run.assert_called_once_with([str(executable), "--check-permissions"], capture_output=True, text=True, timeout=5)
    launch.assert_called_once_with([str(executable)])


def test_platform_checks_and_settings(monkeypatch):
    launch = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(accessibility.sys, "platform", "linux")
    assert accessibility.is_accessibility_granted()
    assert accessibility.request_accessibility()
    assert microphone.is_microphone_granted()
    accessibility.open_accessibility_settings()
    microphone.open_microphone_settings()
    launch.assert_not_called()
    monkeypatch.setattr(accessibility.sys, "platform", "darwin")
    accessibility.open_accessibility_settings()
    microphone.open_microphone_settings()
    assert launch.call_args_list == [((["open", accessibility.ACCESSIBILITY_SETTINGS_URL],),), ((["open", microphone.MICROPHONE_SETTINGS_URL],),)]
