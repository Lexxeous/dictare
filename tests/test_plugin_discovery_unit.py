"""Plugin discovery handles broken and duplicate extensions safely."""

from types import SimpleNamespace
from unittest.mock import Mock

import dictare.plugins as plugins
from dictare.plugins.base import BasePlugin


class ExamplePlugin(BasePlugin):
    name = "example"
    description = "example plugin"

    def get_commands(self):
        return None


def test_base_plugin_requires_loading():
    plugin = ExamplePlugin()
    try:
        plugin.services
    except RuntimeError as exc:
        assert "example" in str(exc)
    else:
        raise AssertionError("unloaded plugin exposed services")
    services = object()
    plugin.on_load(services)
    assert plugin.services is services and plugin.get_commands() is None


def test_entrypoints_skip_invalid_and_broken(monkeypatch, caplog):
    import importlib.metadata

    valid = SimpleNamespace(name="valid", load=lambda: ExamplePlugin)
    invalid = SimpleNamespace(name="invalid", load=lambda: object)
    broken = SimpleNamespace(name="broken", load=Mock(side_effect=ValueError("bad plugin")))
    entry_points = Mock(return_value=[valid, invalid, broken])
    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points)
    assert list(plugins._discover_entrypoint_plugins()) == [ExamplePlugin]
    entry_points.assert_called_once_with(group="dictare.plugins")
    assert "bad plugin" in caplog.text


def test_user_plugin_file_package_and_errors(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(plugins, "get_user_plugins_dir", lambda: tmp_path)
    (tmp_path / "valid.py").write_text("from dictare.plugins.base import BasePlugin\nclass Mine(BasePlugin):\n name='mine'\n description='hello'\n def get_commands(self): return None\n")
    package = tmp_path / "pack"
    package.mkdir()
    (package / "__init__.py").write_text("from dictare.plugins.base import BasePlugin\nclass Pack(BasePlugin):\n name='pack'\n description='hello'\n def get_commands(self): return None\n")
    (tmp_path / "broken.py").write_text("raise RuntimeError('bad extension')")
    (tmp_path / "ignore.txt").write_text("not python")
    found = list(plugins._discover_user_plugins())
    assert {cls().name for cls in found} == {"mine", "pack"}
    assert "bad extension" in caplog.text
    assert plugins._load_user_plugin(tmp_path / "ignore.txt") is None


def test_discovery_deduplicates_and_skips_instantiation_errors(monkeypatch):
    class Broken(ExamplePlugin):
        def __init__(self):
            raise RuntimeError("invalid")

    monkeypatch.setattr(plugins, "_discover_builtin_plugins", lambda: iter([ExamplePlugin, Broken]))
    monkeypatch.setattr(plugins, "_discover_entrypoint_plugins", lambda: iter([ExamplePlugin]))
    monkeypatch.setattr(plugins, "_discover_user_plugins", lambda: iter([]))
    assert plugins.discover_plugins() == [ExamplePlugin]
