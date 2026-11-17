"""Control only a verified checkout-local Dictare development engine."""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def port_in_use(base_url: str) -> bool:
    """Check the local port without assuming the listener is Dictare."""
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ValueError("Expected a loopback development URL with a port")
    try:
        with socket.create_connection((parsed.hostname, parsed.port), timeout=1):
            return True
    except OSError:
        return False


def send_source_command(base_url: str, command: str) -> dict:
    """Verify development identity before sending a source-only command."""
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ValueError("Expected a loopback development URL with a port")
    try:
        with urlopen(base_url + "/api/dev/identity", timeout=5) as response:
            identity = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError(
                "The running engine does not support source identity; stop it from its original terminal."
            ) from exc
        raise
    checkout = os.environ.get("DICTARE_DEV_CHECKOUT")
    if not checkout or not isinstance(identity, dict) or identity.get("source") is not True or identity.get("checkout") != checkout:
        raise ValueError("The engine did not identify itself as this checkout’s source instance")
    hotkey = command == "dev.hotkey"
    request = Request(
        base_url + ("/api/dev/hotkey" if hotkey else "/api/dev/control"),
        data=json.dumps({} if hotkey else {"command": command}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get("status") != "ok":
        detail = result.get("error", "The engine did not accept the request") if isinstance(result, dict) else "Invalid engine response"
        raise ValueError(str(detail))
    return result


def wait_for_port_close(base_url: str, timeout: float = 10.0) -> bool:
    """Wait until a requested source shutdown releases its port."""
    deadline = time.monotonic() + timeout
    while port_in_use(base_url):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: dev_control.py URL COMMAND", file=sys.stderr)
        return 2
    base_url, command = sys.argv[1:]
    try:
        if command == "probe":
            return 0 if port_in_use(base_url) else 1
        result = send_source_command(base_url, command)
        if command == "engine.shutdown":
            if not wait_for_port_close(base_url):
                print("Stop requested, but the source port is still in use.", file=sys.stderr)
                return 1
            print("Source engine stopped.")
        else:
            print(json.dumps(result))
        return 0
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        print(f"Source engine control failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
