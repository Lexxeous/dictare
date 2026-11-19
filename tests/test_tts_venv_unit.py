"""Test TTS environment management with subprocess calls replaced."""

import subprocess
from unittest.mock import Mock

import pytest

from dictare.tts import venv


@pytest.fixture
def root(monkeypatch, tmp_path):
    monkeypatch.setattr(venv, "_VENV_ROOT", tmp_path)
    return tmp_path


def test_environment_paths_and_uninstall(root):
    assert venv.get_venv_python("say") is None
    assert venv.get_venv_bin_dir("say") is None
    assert not venv.is_venv_installed("piper")
    python = root / "piper" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    assert venv.get_venv_python("piper") == str(python)
    assert venv.get_venv_bin_dir("piper") == python.parent
    assert venv.is_venv_installed("piper")
    assert venv.uninstall_venv("piper")
    assert not python.exists()
    with pytest.raises(ValueError):
        venv.uninstall_venv("unknown")


@pytest.mark.parametrize("uv", [None, "/test/uv"])
def test_install_commands_and_progress(root, monkeypatch, uv):
    monkeypatch.setattr(venv, "_find_uv", lambda: uv)
    run = Mock()
    monkeypatch.setattr(venv.subprocess, "run", run)
    progress = []
    assert venv.install_venv("piper", progress.append)
    assert run.call_count == 2
    first, second = [call.args[0] for call in run.call_args_list]
    if uv:
        assert first[:3] == [uv, "venv", "--python"]
        assert second[:4] == [uv, "pip", "install", "--python"]
    else:
        assert first[1:3] == ["-m", "venv"]
        assert second[1:4] == ["-m", "pip", "install"]
    assert "piper-tts" in second and "pydantic" in second
    assert "installed successfully" in progress[-1]


def test_install_failure_cleans_partial_environment(root, monkeypatch):
    monkeypatch.setattr(venv, "_find_uv", lambda: None)
    path = root / "coqui"
    path.mkdir()
    monkeypatch.setattr(venv.subprocess, "run", Mock(side_effect=subprocess.CalledProcessError(1, "python", stderr=b"broken")))
    progress = []
    assert not venv.install_venv("coqui", progress.append)
    assert not path.exists()
    assert "broken" in progress[-1]
    with pytest.raises(ValueError):
        venv.install_venv("unknown")
