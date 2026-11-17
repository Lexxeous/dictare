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
        gate = HoldGate(lambda: events.append('start'), events.append, timeout=5)
        assert gate.press()
        timer = gate._timer
        assert gate.active and not gate.press()
        assert gate.release() and not gate.release()
        assert not gate.active and timer.cancelled
        assert events == ['start', 'released']


def test_lost_release_times_out_and_old_timer_cannot_end_new_hold():
    events = []
    with patch('dictare.hotkey.hold_gate.threading.Timer', Timer):
        gate = HoldGate(lambda: events.append('start'), events.append, timeout=5)
        gate.press()
        old = gate._timer
        old.fire()
        assert not gate.active
        assert events == ['start', 'timeout']
        gate.press()
        old.fire()
        assert gate.active
        assert gate.cancel()
        assert events == ['start', 'timeout', 'start', 'cancelled']


def test_failed_start_and_invalid_timeout_do_not_leave_a_hold_active():
    with pytest.raises(ValueError):
        HoldGate(lambda: None, lambda _: None, timeout=0)
    with patch('dictare.hotkey.hold_gate.threading.Timer', Timer):
        def fail():
            raise RuntimeError('start failed')
        ends = []
        gate = HoldGate(fail, ends.append, timeout=5)
        with pytest.raises(RuntimeError):
            gate.press()
        assert not gate.active
        assert not gate.release()
        assert ends == ["cancelled"]
