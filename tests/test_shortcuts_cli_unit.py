"""Keyboard shortcut configuration without a physical keyboard."""
import builtins
from types import SimpleNamespace

import tomlkit

from dictare.cli import shortcuts


def test_save_shortcuts_preserves_other_config(tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('[other]\nvalue = 1\n')
    index_command = shortcuts.AVAILABLE_COMMANDS[2]
    shortcuts._save_shortcuts({'project-next': 'Ctrl+N', shortcuts._command_key(index_command): 'Alt+1'}, path)
    config = tomlkit.parse(path.read_text())
    assert config['other']['value'] == 1
    assert config['keyboard']['shortcuts'][1]['args']['index'] == 1
    assert config['keyboard']['shortcuts'][0]['keys'] == 'Ctrl+N'


def test_normalization_and_current_shortcuts():
    config = SimpleNamespace(keyboard=SimpleNamespace(shortcuts=[{'command': 'next', 'keys': 'Ctrl+N'}, {'command': 'index', 'keys': 'Alt+1', 'args': {'index': 1}}]))
    assert shortcuts._get_current_shortcuts(config) == {'next': 'Ctrl+N', "index:{'index': 1}": 'Alt+1'}
    assert shortcuts._normalize_shortcut('control-option-shift-meta-a') == 'Ctrl+Alt+Shift+Cmd+A'


def test_interactive_edit_moves_duplicates_deletes_and_saves(monkeypatch, tmp_path, capsys):
    path = tmp_path / 'config.toml'
    config = SimpleNamespace(keyboard=SimpleNamespace(shortcuts=[{'command': 'project-prev', 'keys': 'Ctrl+N'}]))
    monkeypatch.setattr(shortcuts, 'get_config_path', lambda: path)
    monkeypatch.setattr(shortcuts, 'load_config', lambda path: config)
    monkeypatch.setattr(shortcuts, '_capture_shortcut', lambda: 'Ctrl+N')
    answers = iter(['?', 'd bad', 'd 99', '1', 's'])
    monkeypatch.setattr(builtins, 'input', lambda prompt: next(answers))
    shortcuts.configure_shortcuts()
    saved = tomlkit.parse(path.read_text())['keyboard']['shortcuts']
    assert len(saved) == 1 and saved[0]['command'] == 'project-next'
    assert 'moved from project-prev' in capsys.readouterr().out
