"""Signed bundle migration uses temporary directories and no system commands."""

from pathlib import Path
from unittest.mock import Mock

from dictare.daemon import app_bundle


def test_migration_backs_up_existing_bundle_and_installs_signed_copy(tmp_path, monkeypatch):
    source = tmp_path / "cellar" / "Dictare.app"
    launcher = source / "Contents" / "MacOS" / "Dictare"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("signed launcher")
    dest = tmp_path / "Applications" / "Dictare.app"
    dest.mkdir(parents=True)
    (dest / "old").write_text("old bundle")
    monkeypatch.setattr(app_bundle, "_find_cellar_bundle", lambda: source)
    monkeypatch.setattr(app_bundle, "get_app_path", lambda: dest)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(app_bundle.time, "time", lambda: 100)
    run = Mock()
    monkeypatch.setattr(app_bundle.subprocess, "run", run)

    assert app_bundle.migrate_signed_bundle_from_cellar()
    assert (dest / "Contents" / "MacOS" / "Dictare").read_text() == "signed launcher"
    assert (tmp_path / ".dictare/trash/Dictare.app.100/old").read_text() == "old bundle"
    assert run.call_args.args[0] == ["xattr", "-dr", "com.apple.quarantine", str(dest)]


def test_signed_bundle_migration_skips_existing_signed_bundle_unless_forced(tmp_path, monkeypatch):
    source = tmp_path / "source.app"
    source.mkdir()
    (source / "new").touch()
    dest = tmp_path / "Dictare.app"
    marker = dest / "Contents/Resources/launcher_signed"
    marker.parent.mkdir(parents=True)
    marker.touch()
    monkeypatch.setattr(app_bundle, "_find_cellar_bundle", lambda: source)
    monkeypatch.setattr(app_bundle, "get_app_path", lambda: dest)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(app_bundle.subprocess, "run", Mock())
    assert not app_bundle.migrate_signed_bundle_from_cellar()
    assert marker.exists()
    assert app_bundle.migrate_signed_bundle_from_cellar(force=True)
    assert (dest / "new").exists()


def test_signed_bundle_migration_does_nothing_without_source(monkeypatch):
    monkeypatch.setattr(app_bundle, "_find_cellar_bundle", lambda: None)
    assert not app_bundle.migrate_signed_bundle_from_cellar()
