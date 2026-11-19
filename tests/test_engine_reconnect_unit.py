"""Tests for the engine's interruptible audio reconnect loop."""

from unittest.mock import MagicMock

from dictare.core.engine import DictareEngine


def test_run_reconnects_and_releases_lock(monkeypatch):
    engine = DictareEngine.__new__(DictareEngine)
    engine.running = True
    engine.audio_manager = MagicMock(reconnect_reason="stream stopped")
    engine.audio_manager.reconnect.return_value = True
    engine._reconnecting = MagicMock()
    engine._reconnecting.acquire.return_value = True

    def sleep(_delay):
        engine.running = False

    monkeypatch.setattr("dictare.core.engine.time.sleep", sleep)
    engine.run()
    engine.audio_manager.reconnect.assert_called_once_with(engine.audio_manager.on_audio_chunk)
    engine._reconnecting.release.assert_called_once()


def test_run_skips_reconnect_when_lock_is_busy(monkeypatch):
    engine = DictareEngine.__new__(DictareEngine)
    engine.running = True
    engine.audio_manager = MagicMock(reconnect_reason="stream stopped")
    engine._reconnecting = MagicMock()
    engine._reconnecting.acquire.return_value = False
    monkeypatch.setattr("dictare.core.engine.time.sleep", lambda _: setattr(engine, "running", False))
    engine.run()
    engine.audio_manager.reconnect.assert_not_called()
    engine._reconnecting.release.assert_not_called()


def test_run_reconnect_failure_wait_is_interruptible(monkeypatch):
    engine = DictareEngine.__new__(DictareEngine)
    engine.running = True
    engine.audio_manager = MagicMock(reconnect_reason="stream stopped")
    engine.audio_manager.reconnect.return_value = False
    engine._reconnecting = MagicMock()
    engine._reconnecting.acquire.return_value = True
    sleeps = []

    def sleep(delay):
        sleeps.append(delay)
        if delay == 0.5:
            engine.running = False

    monkeypatch.setattr("dictare.core.engine.time.sleep", sleep)
    monkeypatch.setattr("dictare.core.engine.time.monotonic", lambda: 10)
    engine.run()
    assert sleeps == [0.1, 0.5]
    engine._reconnecting.release.assert_called_once()


def test_run_handles_keyboard_interrupt(monkeypatch):
    engine = DictareEngine.__new__(DictareEngine)
    engine.running = True

    def interrupt(_delay):
        raise KeyboardInterrupt

    monkeypatch.setattr("dictare.core.engine.time.sleep", interrupt)
    engine.run()
