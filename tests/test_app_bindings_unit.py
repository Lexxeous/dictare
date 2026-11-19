"""Check input binding lifecycle and command routing."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.app.bindings import KeyboardBindingManager, _BindingCommands


def test_manager_loads_sources_once_and_stops(monkeypatch):
    import dictare.input.manager
    input_manager = Mock(running_sources=["keyboard", "remote"])
    factory = Mock(return_value=input_manager)
    monkeypatch.setattr(dictare.input.manager, "InputManager", factory)
    config = SimpleNamespace(log_level="debug", keyboard=SimpleNamespace(shortcuts={"key": "repeat"}))
    manager = KeyboardBindingManager(Mock(), config)
    assert not manager.is_running and manager.active_sources == []
    manager.start()
    manager.start()
    input_manager.load_keyboard_shortcuts.assert_called_once_with({"key": "repeat"})
    input_manager.load_device_profiles.assert_called_once()
    input_manager.start.assert_called_once()
    assert manager.is_running and manager.active_sources == ["keyboard", "remote"]
    assert factory.call_args.kwargs["verbose"] is True
    manager.stop()
    manager.stop()
    input_manager.stop.assert_called_once()
    assert not manager.is_running and manager.active_sources == []


@pytest.mark.parametrize("command,method,args", [
    ("listening-on", "set_listening", (True,)),
    ("listening-off", "set_listening", (False,)),
    ("toggle-listening", "toggle_listening", ()),
    ("next-agent", "switch_agent", (1,)),
    ("prev-agent", "switch_agent", (-1,)),
    ("repeat", "resend_last", ()),
])
def test_commands_call_engine(command, method, args):
    engine = Mock()
    commands = _BindingCommands(engine)
    assert commands.execute(command)
    getattr(engine, method).assert_called_once_with(*args)


def test_command_arguments_and_failures():
    engine = Mock()
    commands = _BindingCommands(engine)
    assert commands.execute("switch-to-agent", {"name": "shell"})
    engine.switch_to_agent_by_name.assert_called_once_with(name="shell")
    assert not commands.execute("unknown")
    engine.resend_last.side_effect = RuntimeError("unavailable")
    assert not commands.execute("repeat")
