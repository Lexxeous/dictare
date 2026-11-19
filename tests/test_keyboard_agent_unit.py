"""Keyboard agent queues and injector selection without real keystrokes."""

from unittest.mock import MagicMock

import pytest

from dictare.agent.keyboard import KeyboardAgent


@pytest.fixture
def agent():
    config = MagicMock()
    config.output.typing_delay_ms = 10
    config.output.auto_submit = False
    config.output.submit_keys = ["enter"]
    config.output.newline_keys = ["shift", "enter"]
    return KeyboardAgent(config)


@pytest.mark.parametrize("platform,module,cls", [
    ("darwin", "dictare.agent.injection.quartz", "QuartzInjector"),
    ("linux", "dictare.agent.injection.ydotool", "YdotoolInjector"),
])
def test_platform_injector_selection(agent, monkeypatch, platform, module, cls):
    injector = MagicMock()
    monkeypatch.setattr("dictare.agent.keyboard.sys.platform", platform)
    monkeypatch.setattr(f"{module}.{cls}", lambda: injector)
    assert agent._create_injector() is injector
    injector.is_available.return_value = False
    with pytest.raises(RuntimeError, match="not available"):
        agent._create_injector()


def test_worker_send_and_shutdown(agent, monkeypatch):
    injector = MagicMock()
    injector.type_text.return_value = True
    monkeypatch.setattr(agent, "_create_injector", lambda: injector)
    assert agent.send({"text": "ignored"}) is False
    agent.start()
    agent.start()
    try:
        assert agent.send({"text": "hello", "x_input": {"ops": ["submit"]}})
        injector.type_text.assert_called_once_with("hello", delay_ms=10, auto_submit=True, submit_keys=["enter"], newline_keys=["shift", "enter"])
        assert agent.send({"text": "", "visual_newline": True})
        injector.send_newline.assert_called_once()
        assert agent.send({"text": "", "x_input": {"ops": ["submit"]}})
        injector.send_submit.assert_called_once()
    finally:
        agent.stop()
    agent.stop()
    assert agent._injector is None


def test_processing_without_injector_and_timeout_estimate(agent):
    assert agent._process_message({"text": "hello"}) is False
    assert agent._estimate_timeout_seconds({"text": "x" * 100}) == 3.0
    agent.config.output.typing_delay_ms = -10
    assert agent._estimate_timeout_seconds({"text": "x"}) == 2.0
