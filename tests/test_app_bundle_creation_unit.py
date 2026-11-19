"""App bundle creation uses only a temporary directory and fake launchers."""
import plistlib
from unittest.mock import Mock

from dictare.daemon import app_bundle as bundle


def test_create_fallback_bundle_and_skip_unchanged(monkeypatch, tmp_path):
    write_path = Mock()
    fallback = Mock(side_effect=lambda path, python: path.write_text('launcher'))
    icon = Mock()
    monkeypatch.setattr(bundle, 'resolve_service_python_path', lambda path: path)
    monkeypatch.setattr(bundle, '_write_external_python_path', write_path)
    monkeypatch.setattr(bundle, '_get_launcher_source_hash', lambda: 'source-hash')
    monkeypatch.setattr(bundle, '_find_cellar_bundle', lambda: None)
    monkeypatch.setattr(bundle, '_build_native_launcher', lambda path: False)
    monkeypatch.setattr(bundle, '_write_bash_launcher', fallback)
    monkeypatch.setattr(bundle, '_copy_icns', icon)
    app = bundle.create_app_bundle('/test/python', tmp_path)
    contents = app / 'Contents'
    info = plistlib.loads((contents / 'Info.plist').read_bytes())
    assert info['CFBundleIdentifier'] == bundle.BUNDLE_ID
    assert info['CFBundleExecutable'] == bundle.APP_NAME
    assert (contents / 'MacOS' / 'launcher_hash').read_text() == 'source-hash'
    assert (contents / 'MacOS' / bundle.APP_NAME).read_text() == 'launcher'
    assert bundle.create_app_bundle('/test/python', tmp_path) == app
    fallback.assert_called_once()
    assert write_path.call_count == 2
    icon.assert_called_once()


def test_signed_launcher_is_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr(bundle, 'resolve_service_python_path', lambda path: path)
    monkeypatch.setattr(bundle, '_write_external_python_path', Mock())
    monkeypatch.setattr(bundle, '_get_launcher_source_hash', lambda: 'new')
    app = tmp_path / f'{bundle.APP_NAME}.app'
    macos = app / 'Contents' / 'MacOS'
    macos.mkdir(parents=True)
    (macos / bundle.APP_NAME).write_text('signed')
    (macos / 'launcher_signed').write_text('true')
    assert bundle.create_app_bundle('/python', tmp_path) == app
    assert (macos / bundle.APP_NAME).read_text() == 'signed'


def test_create_prebuilt_and_cellar_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(bundle, 'resolve_service_python_path', lambda path: path)
    monkeypatch.setattr(bundle, '_write_external_python_path', Mock())
    monkeypatch.setattr(bundle, '_get_launcher_source_hash', lambda: 'hash')
    monkeypatch.setattr(bundle, '_copy_icns', Mock())
    monkeypatch.setattr(bundle, '_install_prebuilt_launcher', lambda source, dest: dest.write_text('signed') or True)
    app = bundle.create_app_bundle('/python', tmp_path, tmp_path / 'prebuilt')
    assert (app / 'Contents/MacOS/launcher_signed').exists()
    other = tmp_path / 'other'
    cellar = tmp_path / 'cellar'
    install = Mock()
    monkeypatch.setattr(bundle, '_find_cellar_bundle', lambda: cellar)
    monkeypatch.setattr(bundle, '_install_cellar_bundle', install)
    result = bundle.create_app_bundle('/python', other)
    install.assert_called_once_with(cellar, result)
