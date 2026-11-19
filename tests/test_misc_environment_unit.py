"""Python environment diagnostics."""
from dictare.cli import misc


def test_supported_python_is_silent(monkeypatch, capsys):
    monkeypatch.setattr(misc.sys, 'version_info', (3, 11, 0))
    misc.check_python_environment()
    assert not capsys.readouterr().err


def test_pyenv_shim_explains_path_fix(monkeypatch, capsys):
    monkeypatch.setattr(misc.sys, 'version_info', (3, 12, 0))
    monkeypatch.setattr(misc.sys, 'executable', '/home/user/.pyenv/shims/python')
    misc.check_python_environment()
    assert 'pyenv' in capsys.readouterr().err


def test_uv_environment_explains_fix(monkeypatch, capsys):
    monkeypatch.setattr(misc.sys, 'version_info', (3, 12, 0))
    monkeypatch.setattr(misc.sys, 'executable', '/tmp/project/.venv/bin/python')
    misc.check_python_environment()
    assert 'uv run' in capsys.readouterr().err
