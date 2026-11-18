from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from pathlib import Path

from dictare.hotkey.ipc import HotkeyIPCServer


def _short_socket_path() -> Path:
    # macOS AF_UNIX has a short path limit (~104 bytes including terminator).
    return Path("/tmp") / f"dictare-hk-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"

def _send_line(path: Path, payload: str) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(1.0)
        client.connect(str(path))
        client.sendall(payload.encode("utf-8"))
        data = client.recv(1024)
        return data.decode("utf-8")

def test_hotkey_ipc_ack_and_callback() -> None:
    calls: list[str] = []
    path = _short_socket_path()
    srv = HotkeyIPCServer(on_tap=lambda: calls.append("tap"), socket_path=path, accept_timeout=0.01)
    srv.start()
    try:
        response = _send_line(path, '{"type":"hotkey.tap","seq":7,"ts":1.23}\n')
        assert calls == ["tap"]
        ack = json.loads(response.strip())
        assert ack == {"type": "ack", "seq": 7}
    finally:
        srv.stop()

def test_hotkey_ipc_ignores_invalid_payload() -> None:
    calls: list[str] = []
    path = _short_socket_path()
    srv = HotkeyIPCServer(on_tap=lambda: calls.append("tap"), socket_path=path, accept_timeout=0.01)
    srv.start()
    try:
        # Unknown type: no callback, no ACK required.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(str(path))
            client.sendall(b'{"type":"other","seq":1}\n')
            time.sleep(0.05)
        assert calls == []
    finally:
        srv.stop()


def test_capabilities_report_selected_transport() -> None:
    for paired in (False, True):
        path = _short_socket_path()
        srv = HotkeyIPCServer(
            on_tap=lambda: None, socket_path=path, accept_timeout=0.01,
            paired_gestures=paired,
        )
        srv.start()
        try:
            response = _send_line(path, '{"type":"hotkey.capabilities","seq":42}\n')
            assert json.loads(response) == {
                "type": "ack", "seq": 42, "paired_gestures": paired,
            }
        finally:
            srv.stop()


def test_paired_gesture_release_and_disconnect() -> None:
    calls: list[str] = []
    cancelled = threading.Event()
    path = _short_socket_path()

    def cancel() -> None:
        calls.append("cancel")
        cancelled.set()

    srv = HotkeyIPCServer(
        on_tap=lambda: None, on_key_down=lambda: calls.append("down"),
        on_key_up=lambda: calls.append("up"), on_other_key=cancel,
        socket_path=path, accept_timeout=0.01, paired_gestures=True,
    )
    srv.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(path))
            client.sendall((json.dumps({"type": "gesture.begin", "seq": 1, "ts": time.time()}) + "\n").encode())
            assert json.loads(client.recv(1024)) == {"type": "ack", "seq": 1}
            client.sendall(b'{"type":"gesture.end","seq":2}\n')
            assert json.loads(client.recv(1024)) == {"type": "ack", "seq": 2}
        assert calls == ["down", "up"]
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(path))
            client.sendall((json.dumps({"type": "gesture.begin", "seq": 3, "ts": time.time()}) + "\n").encode())
            assert json.loads(client.recv(1024)) == {"type": "ack", "seq": 3}
        assert cancelled.wait(1)
        assert calls == ["down", "up", "down", "cancel"]
        assert not _send_line(path, json.dumps({"type": "gesture.begin", "seq": 4, "ts": time.time() - 10}) + "\n")
        assert calls == ["down", "up", "down", "cancel"]
    finally:
        srv.stop()


def test_paired_health_requires_complete_gesture() -> None:
    path = _short_socket_path()
    cancelled = threading.Event()
    srv = HotkeyIPCServer(
        on_tap=lambda: None, on_key_down=lambda: None,
        on_key_up=lambda: None, on_other_key=cancelled.set,
        socket_path=path, accept_timeout=0.01, paired_gestures=True,
    )
    srv.start()
    try:
        _send_line(path, '{"type":"hotkey.tap","seq":1}\n')
        assert srv._delivered_count == 0
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(path))
            client.sendall((json.dumps({"type": "gesture.begin", "seq": 2, "ts": time.time()}) + "\n").encode())
            assert json.loads(client.recv(1024))["seq"] == 2
            assert srv._delivered_count == 0
        assert cancelled.wait(1)
        assert srv._delivered_count == 0
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(path))
            client.sendall((json.dumps({"type": "gesture.begin", "seq": 3, "ts": time.time()}) + "\n").encode())
            assert json.loads(client.recv(1024))["seq"] == 3
            client.sendall(b'{"type":"gesture.end","seq":4}\n')
            assert json.loads(client.recv(1024))["seq"] == 4
        assert srv._delivered_count == 1
    finally:
        srv.stop()


def test_paired_gesture_rejects_overlap_and_legacy_edges() -> None:
    calls: list[str] = []
    path = _short_socket_path()
    srv = HotkeyIPCServer(
        on_tap=lambda: None, on_key_down=lambda: calls.append("down"),
        on_key_up=lambda: calls.append("up"), on_other_key=lambda: calls.append("cancel"),
        socket_path=path, accept_timeout=0.01, paired_gestures=True,
    )
    srv.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(path))
            begin = json.dumps({"type": "gesture.begin", "seq": 1, "ts": time.time()}) + "\n"
            client.sendall(begin.encode())
            assert json.loads(client.recv(1024))["type"] == "ack"
            assert not _send_line(path, begin)
            assert not _send_line(path, '{"type":"key.up","seq":2}\n')
            assert calls == ["down"]
            client.sendall(b'{"type":"gesture.cancel","seq":3}\n')
            assert json.loads(client.recv(1024))["seq"] == 3
        assert calls == ["down", "cancel"]
        assert not _send_line(path, begin)
        assert calls == ["down", "cancel"]
    finally:
        srv.stop()


def test_paired_gesture_cancels_when_server_stops() -> None:
    cancelled = threading.Event()
    path = _short_socket_path()
    srv = HotkeyIPCServer(
        on_tap=lambda: None, on_key_down=lambda: None,
        on_key_up=lambda: None, on_other_key=cancelled.set,
        socket_path=path, accept_timeout=0.01, paired_gestures=True,
    )
    srv.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(path))
            client.sendall((json.dumps({"type": "gesture.begin", "seq": 1, "ts": time.time()}) + "\n").encode())
            assert json.loads(client.recv(1024))["seq"] == 1
            srv.stop()
            assert cancelled.wait(1)
    finally:
        srv.stop()


def test_paired_gesture_rejects_out_of_order_end() -> None:
    calls: list[str] = []
    cancelled = threading.Event()
    path = _short_socket_path()

    def cancel() -> None:
        calls.append("cancel")
        cancelled.set()

    srv = HotkeyIPCServer(
        on_tap=lambda: None, on_key_down=lambda: calls.append("down"),
        on_key_up=lambda: calls.append("up"), on_other_key=cancel,
        socket_path=path, accept_timeout=0.01, paired_gestures=True,
    )
    srv.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(path))
            client.sendall((json.dumps({"type": "gesture.begin", "seq": 7, "ts": time.time()}) + "\n").encode())
            assert json.loads(client.recv(1024))["seq"] == 7
            client.sendall(b'{"type":"gesture.end","seq":7}\n')
            assert not client.recv(1024)
        assert cancelled.wait(1)
        assert calls == ["down", "cancel"]
    finally:
        srv.stop()


def test_paired_gesture_cancels_when_begin_ack_is_lost() -> None:
    entered = threading.Event()
    unblock = threading.Event()
    cancelled = threading.Event()
    calls: list[str] = []
    path = _short_socket_path()

    def down() -> None:
        calls.append("down")
        entered.set()
        assert unblock.wait(2)

    def cancel() -> None:
        calls.append("cancel")
        cancelled.set()

    srv = HotkeyIPCServer(
        on_tap=lambda: None, on_key_down=down, on_key_up=lambda: calls.append("up"),
        on_other_key=cancel, socket_path=path, accept_timeout=0.01, paired_gestures=True,
    )
    srv.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(path))
            client.sendall((json.dumps({"type": "gesture.begin", "seq": 1, "ts": time.time()}) + "\n").encode())
            assert entered.wait(1)
        unblock.set()
        assert cancelled.wait(1)
        assert calls == ["down", "cancel"]
    finally:
        unblock.set()
        srv.stop()
