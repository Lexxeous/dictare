"""Source controls never send lifecycle commands to unidentified engines."""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

path = Path(__file__).parents[1] / "scripts" / "dev_control.py"
spec = importlib.util.spec_from_file_location("dev_control", path)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def response(data):
    stream = io.BytesIO(json.dumps(data).encode())
    return stream


def test_stop_only_targets_verified_source_instance(monkeypatch):
    monkeypatch.setenv("DICTARE_DEV_CHECKOUT", "/source")
    requests = []
    def open_url(request, timeout):
        requests.append(request)
        if isinstance(request, str):
            return response({"source": True, "checkout": "/source"})
        assert json.loads(request.data) == {"command": "engine.shutdown"}
        return response({"status": "ok"})
    monkeypatch.setattr(module, "urlopen", open_url)
    assert module.send_source_command("http://127.0.0.1:18770", "engine.shutdown") == {"status": "ok"}
    assert requests[0].endswith("/api/dev/identity")
    assert requests[1].full_url == "http://127.0.0.1:18770/api/dev/control"


def test_unidentified_engine_never_receives_stop(monkeypatch):
    monkeypatch.setenv("DICTARE_DEV_CHECKOUT", "/source")
    open_url = MagicMock(return_value=response({"source": False}))
    monkeypatch.setattr(module, "urlopen", open_url)
    with pytest.raises(ValueError, match="did not identify"):
        module.send_source_command("http://127.0.0.1:8770", "engine.shutdown")
    assert open_url.call_count == 1
    with pytest.raises(ValueError, match="loopback"):
        module.send_source_command("http://example.com:8770", "engine.shutdown")
    assert open_url.call_count == 1


def test_rejected_source_command_is_not_reported_as_success(monkeypatch):
    monkeypatch.setenv("DICTARE_DEV_CHECKOUT", "/source")
    replies = iter([response({"source": True, "checkout": "/source"}), response({"status": "error", "error": "Resolve the pending prompt"})])
    monkeypatch.setattr(module, "urlopen", lambda request, timeout: next(replies))
    with pytest.raises(ValueError, match="Resolve the pending prompt"):
        module.send_source_command("http://127.0.0.1:18770", "engine.shutdown")


def test_probe_detects_an_occupied_local_port_without_sending_commands(monkeypatch):
    connection = MagicMock()
    connector = MagicMock(return_value=connection)
    monkeypatch.setattr(module.socket, "create_connection", connector)
    assert module.port_in_use("http://127.0.0.1:18770")
    connector.assert_called_once_with(("127.0.0.1", 18770), timeout=1)


def test_other_checkout_never_receives_stop(monkeypatch):
    monkeypatch.setenv("DICTARE_DEV_CHECKOUT", "/source")
    open_url = MagicMock(return_value=response({"source": True, "checkout": "/other"}))
    monkeypatch.setattr(module, "urlopen", open_url)
    with pytest.raises(ValueError, match="did not identify"):
        module.send_source_command("http://127.0.0.1:18770", "engine.shutdown")
    assert open_url.call_count == 1


def test_stop_waits_until_port_is_released(monkeypatch):
    states = iter([True, True, False])
    monkeypatch.setattr(module, "port_in_use", lambda url: next(states))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    assert module.wait_for_port_close("http://127.0.0.1:18770")


def test_older_engine_without_identity_has_clear_recovery(monkeypatch):
    from urllib.error import HTTPError

    open_url = MagicMock(side_effect=HTTPError("http://127.0.0.1:18770/api/dev/identity", 404, "missing", {}, None))
    monkeypatch.setattr(module, "urlopen", open_url)
    monkeypatch.setenv("DICTARE_DEV_CHECKOUT", "/source")
    with pytest.raises(ValueError, match="stop it from its original terminal"):
        module.send_source_command("http://127.0.0.1:18770", "engine.shutdown")
    assert open_url.call_count == 1
