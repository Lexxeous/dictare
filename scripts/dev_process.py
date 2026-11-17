"""Own one source process group and optionally honor Dictare's restart exit."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import threading
from types import FrameType


def supervise(command: list[str], restart_on: int | None = None) -> int:
    child: subprocess.Popen | None = None
    requested_signal = 0
    deadline: threading.Timer | None = None

    def terminate_group(signum: int) -> None:
        if child is not None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    def force_stop() -> None:
        if child is not None and child.poll() is None:
            terminate_group(signal.SIGKILL)

    def stop(signum: int, frame: FrameType | None) -> None:
        nonlocal requested_signal, deadline
        requested_signal = requested_signal or signum
        if child is not None and child.poll() is None:
            terminate_group(signum)
            if deadline is None:
                deadline = threading.Timer(5, force_stop)
                deadline.daemon = True
                deadline.start()

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        while not requested_signal:
            child = subprocess.Popen(command, start_new_session=True)
            if requested_signal:
                stop(requested_signal, None)
            code = child.wait()
            # Terminate only descendants of the process group created above.
            terminate_group(signal.SIGTERM)
            if requested_signal:
                return 128 + requested_signal
            if restart_on is None or code != restart_on:
                return code if code >= 0 else 128 - code
            print("Dictare SOURCE: restarting after settings change…", flush=True)
        return 128 + requested_signal
    finally:
        if deadline is not None:
            deadline.cancel()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart-on", type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Provide a source command to run")
    raise SystemExit(supervise(command, args.restart_on))


if __name__ == "__main__":
    main()
