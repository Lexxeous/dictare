"""System settings routes exercise macOS operations without changing the host."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException

from dictare.core.http_routes_settings import register_settings_routes


@pytest.fixture
def routes():
    app = FastAPI()
    register_settings_routes(app, SimpleNamespace())
    return {(route.path, method): route.endpoint for route in app.routes if hasattr(route, 'methods') for method in route.methods}


def call(endpoint, body=None):
    async def json():
        return body or {}
    return asyncio.run(endpoint(SimpleNamespace(json=json))) if body is not None else asyncio.run(endpoint())


def test_launch_at_login(monkeypatch, routes):
    import dictare.daemon.launchd as launchd
    monkeypatch.setattr('sys.platform', 'darwin')
    enabled, disabled = Mock(), Mock()
    monkeypatch.setattr(launchd, 'launch_at_login_enabled', lambda: True)
    monkeypatch.setattr(launchd, 'enable_launch_at_login', enabled)
    monkeypatch.setattr(launchd, 'disable_launch_at_login', disabled)
    assert call(routes['/api/system', 'GET']) == {'platform': 'darwin', 'launch_at_login': True}
    assert call(routes['/api/system', 'POST'], {'launch_at_login': True}) == {'ok': True}
    call(routes['/api/system', 'POST'], {'launch_at_login': False})
    enabled.assert_called_once_with()
    disabled.assert_called_once_with()


def test_hotkey_runtime_and_legacy_status(monkeypatch, routes, tmp_path):
    import dictare.hotkey.runtime_status as runtime
    import dictare.utils.paths as paths
    monkeypatch.setattr('sys.platform', 'darwin')
    monkeypatch.setattr(runtime, 'read_runtime_status', lambda: {'status': 'ready', 'capture_healthy': True})
    assert call(routes['/api/hotkey/status', 'GET']) == {'status': 'ready', 'active_provider': 'none', 'capture_healthy': True}
    monkeypatch.setattr(runtime, 'read_runtime_status', lambda: None)
    monkeypatch.setattr(paths, 'get_dictare_dir', lambda: tmp_path)
    assert call(routes['/api/hotkey/status', 'GET']) == {'status': 'unknown'}
    (tmp_path / 'hotkey_status').write_text('active\n')
    assert call(routes['/api/hotkey/status', 'GET']) == {'status': 'active'}


def test_permissions_operations(monkeypatch, routes):
    import dictare.platform.permission_doctor as module
    monkeypatch.setattr('sys.platform', 'darwin')
    doctor = Mock()
    doctor.run_probe.return_value = {'pressed': True}
    monkeypatch.setattr(module, 'PermissionDoctor', lambda: doctor)
    monkeypatch.setattr(module, 'status_to_dict', lambda status: {'details': 'ok'})
    assert call(routes['/api/permissions/doctor', 'GET']) == {'platform': 'darwin', 'status': 'ok', 'details': 'ok'}
    assert call(routes['/api/permissions/doctor/open', 'POST'], {'target': 'microphone'}) == {'ok': True}
    doctor.open_settings.assert_called_once_with('microphone')
    with pytest.raises(HTTPException) as error:
        call(routes['/api/permissions/doctor/open', 'POST'], {'target': 'invalid'})
    assert error.value.status_code == 400
    assert call(routes['/api/permissions/doctor/probe', 'POST'], {'timeout': '2'}) == {'pressed': True}
    doctor.run_probe.assert_called_once_with(timeout_s=2.0)


def test_fix_hotkey_opens_settings(monkeypatch, routes):
    import subprocess
    monkeypatch.setattr('sys.platform', 'darwin')
    popen = Mock()
    monkeypatch.setattr(subprocess, 'Popen', popen)
    assert call(routes['/api/hotkey/fix', 'POST']) == {'ok': True}
    assert popen.call_args.args[0][0] == 'open'
    assert 'Privacy_ListenEvent' in popen.call_args.args[0][1]
