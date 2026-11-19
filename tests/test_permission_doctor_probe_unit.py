"""Permission diagnostics and runtime hotkey probing."""
from unittest.mock import Mock

import pytest

from dictare.platform import permission_doctor as doctor


def status(**changes):
    values = dict(accessibility=True, microphone=True, input_monitoring=True,
                  hotkey_status='active', capture_healthy=False, active_provider='eventtap')
    values.update(changes)
    return doctor.DoctorStatus(**values)


@pytest.mark.parametrize(('changes', 'code'), [
    ({'microphone': False}, 'missing_microphone'),
    ({'input_monitoring': False}, 'missing_input_monitoring'),
    ({'hotkey_status': 'failed'}, 'tap_creation_failed'),
    ({'capture_healthy': True}, 'ok'),
    ({}, 'granted_but_no_delivery'),
    ({'hotkey_status': 'unknown', 'accessibility': False}, 'accessibility_unconfirmed'),
    ({'hotkey_status': 'unknown'}, 'unknown_state'),
])
def test_diagnosis_covers_recovery_states(changes, code):
    result = doctor.PermissionDoctor().diagnose(status(**changes))
    assert result.code == code
    assert result.steps


def test_probe_reports_delivered_event(monkeypatch):
    instance = doctor.PermissionDoctor()
    monkeypatch.setattr(instance, '_delivered_count', Mock(side_effect=[3, 4]))
    monkeypatch.setattr(instance, 'get_status', lambda: status(capture_healthy=True))
    result = instance.run_probe()
    assert result['ok'] is True
    assert result['delivered_count'] == 4
    assert result['diagnosis']['code'] == 'ok'


def test_probe_timeout_reports_current_status(monkeypatch):
    instance = doctor.PermissionDoctor()
    monkeypatch.setattr(instance, '_delivered_count', Mock(return_value=3))
    monkeypatch.setattr(instance, 'get_status', lambda: status())
    monkeypatch.setattr(doctor.time, 'time', Mock(side_effect=[0, 31]))
    result = instance.run_probe(timeout_s=30)
    assert result['ok'] is False
    assert result['delivered_count'] == 3
    assert result['diagnosis']['code'] == 'granted_but_no_delivery'


@pytest.mark.parametrize(('target', 'function'), [
    ('input_monitoring', 'open_input_monitoring_settings'),
    ('accessibility', 'open_accessibility_settings'),
    ('microphone', 'open_microphone_settings'),
])
def test_open_settings_dispatches(monkeypatch, target, function):
    opened = Mock()
    monkeypatch.setattr(doctor, function, opened)
    doctor.PermissionDoctor().open_settings(target)
    opened.assert_called_once_with()


def test_runtime_counter_handles_invalid_values(monkeypatch):
    monkeypatch.setattr(doctor, 'read_runtime_status', lambda: {'delivered_count': 'invalid'})
    assert doctor.PermissionDoctor._delivered_count() == 0
