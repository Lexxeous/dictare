"""Runtime lifecycle behavior without touching the user's installation."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from dictare import runtime_store as store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    root = tmp_path / 'runtime'
    for name, path in {
        'RUNTIME_ROOT': root, 'VERSIONS_DIR': root / 'versions',
        'CURRENT_LINK': root / 'current', 'PREVIOUS_LINK': root / 'previous',
        'LOCK_DIR': root / 'locks', 'BIN_DIR': tmp_path / 'bin',
        'SHIM_PATH': tmp_path / 'bin' / 'dictare',
    }.items():
        monkeypatch.setattr(store, name, path)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    return root


def test_missing_runtime_and_rollback(isolated_store):
    assert store.resolve_service_python_path('fallback') == 'fallback'
    assert store.snapshot().current_version is None
    with pytest.raises(RuntimeError, match='not initialized'):
        store.runtime_python()
    with pytest.raises(RuntimeError, match='No previous'):
        store.rollback_runtime()


def test_shim_replaces_existing_file_and_is_idempotent(isolated_store):
    store.BIN_DIR.mkdir()
    store.SHIM_PATH.write_bytes(b'\xff')
    assert store.ensure_shim() == store.SHIM_PATH
    assert 'current/bin/dictare' in store.SHIM_PATH.read_text()
    assert store.SHIM_PATH.stat().st_mode & 0o777 == 0o755
    backups = list((Path.home() / '.dictare' / 'trash').iterdir())
    assert len(backups) == 1 and backups[0].read_bytes() == b'\xff'
    store.ensure_shim()
    assert len(list(backups[0].parent.iterdir())) == 1


def test_backup_handles_name_collision_and_broken_symlink(isolated_store):
    path = Path.home() / 'old'
    path.symlink_to(Path.home() / 'missing')
    first = store.backup_existing_path(path)
    assert first.is_symlink()
    path.write_text('second')
    second = store.backup_existing_path(path)
    assert second != first and second.read_text() == 'second'
    assert store.backup_existing_path(path) is None


def test_install_creates_environment_and_reinstalls(isolated_store, monkeypatch):
    calls = []
    monkeypatch.setattr(store, '_run', lambda cmd: calls.append(cmd))
    monkeypatch.setattr(store, 'smoke_test', lambda path, expected_version: calls.append((path, expected_version)))
    target = store.install_runtime('2.0', source='/tmp/package', extras=['tray'], reinstall=True)
    assert calls[0][:4] == ['uv', 'venv', '--python', '3.11']
    assert '--reinstall' in calls[1]
    assert calls[1][-1] == f'dictare[tray] @ {Path("/tmp/package").resolve().as_uri()}'
    assert calls[2] == (target, '2.0')


def test_incomplete_runtime_rejected(isolated_store):
    (store.VERSIONS_DIR / 'bad').mkdir(parents=True)
    with pytest.raises(RuntimeError, match='incomplete'):
        store.install_runtime('bad')


def test_smoke_test_validates_output(tmp_path, monkeypatch):
    monkeypatch.setattr(store.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='Dictare 1.2', stderr=''))
    store.smoke_test(tmp_path, '1.2')
    with pytest.raises(RuntimeError, match='unexpected version'):
        store.smoke_test(tmp_path, '3.0')


@pytest.mark.parametrize(('system', 'machine', 'expected'), [
    ('darwin', 'arm64', ['mlx']), ('darwin', 'x86_64', []), ('linux', 'x86_64', ['tray']),
])
def test_default_extras(system, machine, expected, monkeypatch):
    monkeypatch.setattr(store.sys, 'platform', system)
    monkeypatch.setattr(store.platform, 'machine', lambda: machine)
    assert store.default_extras() == expected


def test_source_url_and_missing_command(monkeypatch):
    assert store.package_spec('1', extras=[], source='https://example.test/pkg') == 'dictare @ https://example.test/pkg'
    def missing(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(store.subprocess, 'run', missing)
    with pytest.raises(RuntimeError, match='Required command not found: uv'):
        store._run(['uv'])
