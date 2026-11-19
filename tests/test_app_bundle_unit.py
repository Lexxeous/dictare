"""App bundle creation with all artifacts in temporary directories."""
import plistlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dictare.daemon import app_bundle


@pytest.fixture
def bundle_environment(monkeypatch):
    monkeypatch.setattr(app_bundle, 'resolve_service_python_path', lambda path: path)
    write_path = Mock()
    monkeypatch.setattr(app_bundle, '_write_external_python_path', write_path)
    monkeypatch.setattr(app_bundle, '_get_launcher_source_hash', lambda: 'hash')
    monkeypatch.setattr(app_bundle, '_get_version', lambda: '1.2.3')
    monkeypatch.setattr(app_bundle, '_find_cellar_bundle', lambda: None)
    monkeypatch.setattr(app_bundle, '_build_native_launcher', lambda path: False)
    monkeypatch.setattr(app_bundle, '_copy_icns', Mock())
    return write_path


def test_create_bundle_falls_back_to_script_and_reuses_unchanged(bundle_environment, tmp_path):
    app = app_bundle.create_app_bundle('/python', app_dir=tmp_path)
    contents = app / 'Contents'
    info = plistlib.loads((contents / 'Info.plist').read_bytes())
    assert info['CFBundleVersion'] == '1.2.3'
    assert info['LSUIElement'] is True
    launcher = contents / 'MacOS' / app_bundle.APP_NAME
    assert '/python -m dictare serve' in launcher.read_text()
    assert launcher.stat().st_mode & 0o100
    assert app_bundle.create_app_bundle('/other-python', app_dir=tmp_path) == app
    assert '/python -m dictare serve' in launcher.read_text()
    assert bundle_environment.call_args.args == ('/other-python',)


def test_create_bundle_installs_prebuilt_launcher(monkeypatch, bundle_environment, tmp_path):
    prebuilt = tmp_path / 'signed'
    prebuilt.write_text('binary')
    monkeypatch.setattr(app_bundle, '_install_prebuilt_launcher', lambda source, dest: (dest.write_text(source.read_text()) > 0))
    app = app_bundle.create_app_bundle('/python', app_dir=tmp_path, prebuilt_launcher=prebuilt)
    assert (app / 'Contents/MacOS/launcher_signed').exists()
    assert (app / 'Contents/MacOS' / app_bundle.APP_NAME).read_text() == 'binary'


def test_prebuilt_launcher_requires_valid_signature(monkeypatch, tmp_path):
    source, dest = tmp_path / 'source', tmp_path / 'dest'
    assert not app_bundle._install_prebuilt_launcher(source, dest)
    source.write_text('binary')
    run = Mock(return_value=SimpleNamespace(returncode=1, stderr='invalid'))
    monkeypatch.setattr(app_bundle.subprocess, 'run', run)
    assert not app_bundle._install_prebuilt_launcher(source, dest)
    assert not dest.exists()
    run.return_value = SimpleNamespace(returncode=0, stderr='')
    assert app_bundle._install_prebuilt_launcher(source, dest)
    assert dest.read_text() == 'binary'
    assert dest.stat().st_mode & 0o100


def test_find_cellar_bundle_uses_valid_hint(monkeypatch, tmp_path):
    invalid = tmp_path / 'invalid.app'
    valid = tmp_path / 'valid.app'
    launcher = valid / 'Contents/MacOS' / app_bundle.APP_NAME
    launcher.parent.mkdir(parents=True)
    launcher.touch()
    monkeypatch.setattr(app_bundle, '_candidate_homebrew_bundle_paths', lambda: [invalid, valid])
    assert app_bundle._find_cellar_bundle() == valid
