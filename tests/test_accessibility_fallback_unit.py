"""Exercise native accessibility checks without calling macOS APIs."""
import ctypes
from unittest.mock import Mock

import pytest

from dictare.daemon import app_bundle
from dictare.platform import accessibility


@pytest.mark.parametrize("prompt", [True, False])
def test_ctypes_fallback_checks_and_releases_options(monkeypatch, prompt):
    monkeypatch.setattr(app_bundle, "get_executable_path", lambda: None)
    appserv = Mock()
    appserv.AXIsProcessTrustedWithOptions.return_value = 1
    core = Mock()
    core.CFDictionaryCreateMutable.return_value = "options"
    monkeypatch.setattr(ctypes.cdll, "LoadLibrary", lambda name: core if "CoreFoundation" in name else appserv)

    class Pointer:
        @staticmethod
        def in_dll(library, name):
            return name

    monkeypatch.setattr(ctypes, "c_void_p", Pointer)
    assert accessibility._check_ax_trusted(prompt) is True
    core.CFDictionarySetValue.assert_called_once_with(
        "options", "kAXTrustedCheckOptionPrompt", "kCFBooleanTrue" if prompt else "kCFBooleanFalse"
    )
    core.CFRelease.assert_called_once_with("options")
