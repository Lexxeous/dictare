"""Preflight and open the isolated macOS development app window."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BUNDLE = "dev.dragfly.dictare.develop"


def applications(bundle_id: str):
    from AppKit import NSRunningApplication

    return NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)


def stop_app() -> None:
    expected = (Path(os.environ["DICTARE_DEV_CHECKOUT"]) / ".dictare-dev/Dictare Develop.app").resolve()
    running = applications(BUNDLE)
    for app in running:
        url = app.bundleURL()
        if url is None or Path(str(url.path())).resolve() != expected:
            raise RuntimeError("A development app from another checkout is running. Quit it there first.")
    for app in running:
        app.terminate()
    deadline = time.monotonic() + 8
    while any(not app.isTerminated() for app in running) and time.monotonic() < deadline:
        time.sleep(0.1)
    for app in running:
        if not app.isTerminated():
            app.forceTerminate()
    deadline = time.monotonic() + 3
    while any(not app.isTerminated() for app in running) and time.monotonic() < deadline:
        time.sleep(0.1)
    if any(not app.isTerminated() for app in running):
        raise RuntimeError("Could not stop the development app. Quit it in Activity Monitor and retry.")


def preflight(port: int) -> None:
    if subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip() != "develop":
        raise RuntimeError("Switch this checkout to develop before starting the native development app.")
    for bundle in ("dev.dragfly.dictare",):
        if applications(bundle):
            raise RuntimeError(f"{bundle} is already running. Quit it before starting the development app.")
    for label in ("dev.dragfly.dictare", "dev.dragfly.dictare.tray"):
        result = subprocess.run(["launchctl", "list", label], capture_output=True, text=True)
        if result.returncode == 0 and '"PID" =' in result.stdout:
            raise RuntimeError(f"The installed service {label} is running. Stop it before starting the development app.")
    if applications(BUNDLE):
        print("Stopping the existing development app before restarting it.", file=sys.stderr)
        stop_app()
    for checked_port in {port, 8770}:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", checked_port)) == 0:
                raise RuntimeError(f"Port {checked_port} is already in use. Stop the existing Dictare engine or choose a different development port.")
    for app in applications("dev.dragfly.dictare.preview"):
        app.terminate()


def show_window(port: int) -> None:
    from Foundation import NSDistributedNotificationCenter

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/dev/identity", timeout=1) as response:
                import json

                identity = json.load(response)
            if identity.get("checkout") != os.environ["DICTARE_DEV_CHECKOUT"]:
                raise RuntimeError("The running engine does not belong to this checkout.")
            NSDistributedNotificationCenter.defaultCenter().postNotificationName_object_userInfo_deliverImmediately_(
                f"{BUNDLE}.open-window", None, {"host": "127.0.0.1", "port": port}, True
            )
            return
        except (OSError, urllib.error.URLError, ValueError):
            time.sleep(0.5)
    print("Engine did not become ready within 90 seconds; check the native app log.", file=sys.stderr)


def main() -> int:
    try:
        if sys.argv[1] == "preflight":
            preflight(int(sys.argv[2]))
        elif sys.argv[1] == "show":
            show_window(int(sys.argv[2]))
        elif sys.argv[1] == "stop":
            stop_app()
        else:
            raise ValueError("Unknown action")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Native development app: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
