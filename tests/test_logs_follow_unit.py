"""Exercise log-follow output without a long-running process."""

import io
import json

import pytest
import typer
from typer.testing import CliRunner

from dictare.cli import logs


class EndFollowError(Exception):
    pass


class FollowFile(io.StringIO):
    def seek(self, offset, whence=0):
        # Simulate data arriving immediately after seeking to the current end.
        return super().seek(0)


@pytest.mark.parametrize("raw", [False, True])
def test_follow_filters_new_entries(monkeypatch, tmp_path, raw):
    import dictare.logging.setup as setup

    monkeypatch.setattr(setup, "DEFAULT_LOG_DIR", tmp_path)
    (tmp_path / "engine.jsonl").write_text("")
    lines = [
        json.dumps({"source": "tray", "event": "ignore"}),
        json.dumps({"source": "engine", "event": "arrived"}),
    ]
    monkeypatch.setattr(logs, "open", lambda *_: FollowFile("\n".join(lines) + "\n"), raising=False)
    monkeypatch.setattr(logs.time, "sleep", lambda _: (_ for _ in ()).throw(EndFollowError()))
    app = typer.Typer()
    logs.register(app)
    args = ["--follow", "--source", "engine"] + (["--raw"] if raw else [])
    result = CliRunner().invoke(app, args)
    assert isinstance(result.exception, EndFollowError)
    assert "arrived" in result.output
    assert "ignore" not in result.output


def test_follow_plain_log_prints_new_data(monkeypatch, tmp_path, capsys):
    path = tmp_path / "tts-worker.log"
    path.write_text("")
    monkeypatch.setattr(logs, "open", lambda *_: FollowFile("new line\n"), raising=False)
    monkeypatch.setattr(logs.time, "sleep", lambda _: (_ for _ in ()).throw(EndFollowError()))
    with pytest.raises(EndFollowError):
        logs._show_plain_log(path, follow=True, last=0)
    assert capsys.readouterr().out == "new line\n"


def test_rich_output_colors_known_levels(monkeypatch):
    import rich.console

    printed = []
    monkeypatch.setattr(rich.console, "Console", lambda: type("Console", (), {"print": lambda self, line, **kw: printed.append(line)})())
    logs._print_line("12:00  ERROR failed", True)
    logs._print_line("no level", True)
    assert printed == ["12:00  [red bold]ERROR[/] failed", "no level"]
