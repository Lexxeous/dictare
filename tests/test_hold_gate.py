"""A held shortcut must not stay active after its release is lost."""

from unittest.mock import patch

import pytest

from dictare.hotkey.hold_gate import HoldGate


class Timer:
    def __init__(self, interval, callback, args=()):
        self.callback = callback
        self.args = args
        self.cancelled = False
        self.daemon = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback(*self.args)


def test_press_release_and_duplicate_events_are_serialized():
    events = []
    with patch('dictare.hotkey.hold_gate.threading.Timer', Timer):
        gate = HoldGate(lambda token: events.append(('start', token)), lambda reason, token: events.append((reason, token)), timeout=5)
        assert gate.press()
        timer = gate._timer
        assert gate.active and not gate.press()
        assert gate.release() and not gate.release()
        assert not gate.active and timer.cancelled
        assert events == [('start', 1), ('released', 1)]
        assert not gate.press()
        assert not gate.complete(99)
        assert gate.complete(1)
        assert gate.press()
        assert gate.cancel()
        assert not gate.complete(1)
        assert gate.complete(2)


def test_lost_release_times_out_and_old_timer_cannot_end_new_hold():
    events = []
    with patch('dictare.hotkey.hold_gate.threading.Timer', Timer):
        gate = HoldGate(lambda token: events.append(('start', token)), lambda reason, token: events.append((reason, token)), timeout=5)
        gate.press()
        old = gate._timer
        old.fire()
        assert not gate.active
        assert events == [('start', 1), ('timeout', 1)]
        assert not gate.press()
        assert gate.complete(1)
        gate.press()
        old.fire()
        assert gate.active
        assert gate.cancel()
        assert events == [('start', 1), ('timeout', 1), ('start', 2), ('cancelled', 2)]


def test_failed_start_and_invalid_timeout_do_not_leave_a_hold_active():
    with pytest.raises(ValueError):
        HoldGate(lambda _: None, lambda _reason, _token: None, timeout=0)
    with patch('dictare.hotkey.hold_gate.threading.Timer', Timer):
        def fail(_token):
            raise RuntimeError('start failed')
        ends = []
        gate = HoldGate(fail, lambda reason, token: ends.append((reason, token)), timeout=5)
        with pytest.raises(RuntimeError):
            gate.press()
        assert not gate.active
        assert not gate.release()
        assert ends == [("cancelled", 1)]
        assert gate.complete(1)


def test_engine_hotkey_entry_points_preserve_existing_tap_behavior():
    from unittest.mock import MagicMock, call

    from dictare.config import Config
    from dictare.core.engine import DictareEngine

    engine = DictareEngine(Config(), hotkey_enabled=False)
    detector = MagicMock()
    engine.tap_detector = detector
    engine.hotkey_tap()
    engine.hotkey_down()
    engine.hotkey_up()
    engine.hotkey_other_key()
    assert detector.mock_calls == [call.on_key_down(), call.on_key_up(), call.on_key_down(), call.on_key_up(), call.on_other_key()]
