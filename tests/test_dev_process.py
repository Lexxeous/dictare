"""Exercise the source supervisor with disposable child processes, no services."""

import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "dev_process.py"
spec = importlib.util.spec_from_file_location("dev_process", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="The Bash source runner owns POSIX process groups")


def test_source_restart_exit_relaunches_only_that_process(tmp_path):
    counter = tmp_path / "starts"
    code = "from pathlib import Path; import sys; p=Path(sys.argv[1]); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); sys.exit(75 if n==1 else 0)"
    assert module.supervise([sys.executable, "-c", code, str(counter)], restart_on=75) == 0
    assert counter.read_text() == "2"


def test_other_exit_status_is_preserved_without_restart():
    assert module.supervise([sys.executable, "-c", "raise SystemExit(42)"], restart_on=75) == 42


def test_termination_reaches_owned_child_and_prevents_restart(tmp_path):
    marker = tmp_path / "child"
    stopped = tmp_path / "stopped"
    code = "import os,signal,sys,time; from pathlib import Path; signal.signal(signal.SIGTERM, lambda *_: (Path(sys.argv[2]).write_text('stopped'), sys.exit(75))); Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)"
    process = subprocess.Popen([sys.executable, str(SCRIPT), "--restart-on", "75", "--", sys.executable, "-c", code, str(marker), str(stopped)])
    child_pid = None
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "Source child did not start"
        child_pid = int(marker.read_text())
        process.terminate()
        assert process.wait(timeout=5) == 143
        assert stopped.read_text() == "stopped"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if child_pid is not None:
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
