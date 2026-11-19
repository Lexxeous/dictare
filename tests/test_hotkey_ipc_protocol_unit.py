"""Exercise IPC protocol handling without opening a socket."""

import hashlib
import json
from unittest.mock import Mock

import pytest

from dictare.hotkey import ipc


@pytest.mark.parametrize(
    ("message_type", "callback_name", "count"),
    [
        ("hotkey.tap", "on_tap", 1),
        ("key.down", "on_key_down", 1),
        ("key.up", "on_key_up", 1),
        ("other_key", "on_other_key", 0),
        ("key.combo", "on_combo", 0),
    ],
)
def test_protocol_dispatch_and_ack(message_type, callback_name, count):
    callbacks = {name: Mock() for name in ("on_tap", "on_key_down", "on_key_up", "on_other_key", "on_combo")}
    server = ipc.HotkeyIPCServer(**callbacks)
    server._write_runtime_status_locked = Mock()
    conn = Mock()
    payload = json.dumps({"type": message_type, "seq": 12}).encode() + b"\n"
    conn.recv.side_effect = [payload[:4], payload[4:]]

    server._handle_conn(conn)

    callbacks[callback_name].assert_called_once_with()
    assert server._delivered_count == count
    conn.sendall.assert_called_once_with(b'{"type": "ack", "seq": 12}\n')
    conn.close.assert_called_once_with()


@pytest.mark.parametrize("payload", [b"invalid\n", b'{"type":"unknown"}\n', b""])
def test_invalid_or_incomplete_message_is_closed_without_ack(payload):
    server = ipc.HotkeyIPCServer(on_tap=Mock())
    conn = Mock()
    conn.recv.return_value = payload
    server._handle_conn(conn)
    conn.sendall.assert_not_called()
    conn.close.assert_called_once()


@pytest.mark.parametrize("message_type,callback_name", [("hotkey.tap", "on_tap"), ("key.down", "on_key_down"), ("key.up", "on_key_up"), ("other_key", "on_other_key"), ("key.combo", "on_combo")])
def test_callback_exception_does_not_prevent_ack(message_type, callback_name):
    callbacks = {"on_tap": Mock()}
    callbacks[callback_name] = Mock(side_effect=RuntimeError("callback failed"))
    server = ipc.HotkeyIPCServer(**callbacks)
    conn = Mock()
    conn.recv.return_value = json.dumps({"type": message_type, "seq": 5}).encode() + b"\n"
    server._handle_conn(conn)
    conn.sendall.assert_called_once_with(b'{"type": "ack", "seq": 5}\n')
    assert server._delivered_count == 0


def test_launcher_confirmation_hash_tracks_binary_changes(tmp_path, monkeypatch):
    from dictare.daemon import app_bundle

    launcher = tmp_path / "app" / "Contents" / "MacOS" / "Dictare"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"original")
    monkeypatch.setattr(app_bundle, "get_app_path", lambda: tmp_path / "app")
    monkeypatch.setattr(ipc, "get_dictare_dir", lambda: tmp_path)
    assert not ipc.check_confirmed_launcher_hash()
    ipc.HotkeyIPCServer._save_confirmed_launcher_hash()
    assert (tmp_path / "hotkey_confirmed_hash").read_text() == hashlib.sha256(b"original").hexdigest()
    assert ipc.check_confirmed_launcher_hash()
    launcher.write_bytes(b"updated")
    assert not ipc.check_confirmed_launcher_hash()


@pytest.mark.parametrize("launcher_status,expected", [("failed", "failed"), ("active", "active"), ("confirmed", "active"), ("unknown", "unknown")])
def test_runtime_status_reflects_launcher_status(monkeypatch, launcher_status, expected):
    write = Mock()
    monkeypatch.setattr(ipc, "write_runtime_status", write)
    server = ipc.HotkeyIPCServer(on_tap=Mock())
    server._read_launcher_status = Mock(return_value=launcher_status)
    server._write_runtime_status()
    assert write.call_args.args[0]["status"] == expected
    assert write.call_args.args[0]["capture_healthy"] is False
