"""A failed form field must not leave earlier form edits written to disk."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dictare.config import load_config, set_config_values
from dictare.core.http_server import OpenVIPServer
from tests.test_http_server_extra import MockController, MockEngine


@pytest.fixture
def path(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('# Keep this comment\neditor = "old"\n[stt]\nlanguage = "en" # Keep inline\n[future]\nunknown = 42\n')
    monkeypatch.setenv("DICTARE_CONFIG_PATH", str(path))
    return path


def test_invalid_later_value_leaves_file_unchanged(path):
    original = path.read_bytes()
    with pytest.raises(ValueError):
        set_config_values({"stt.language": "it", "server.port": "invalid"}, path)
    assert path.read_bytes() == original


def test_unknown_later_key_leaves_file_unchanged(path):
    original = path.read_bytes()
    with pytest.raises(KeyError):
        set_config_values({"editor": "changed", "unknown": "bad"}, path)
    assert path.read_bytes() == original


def test_success_preserves_comments_unknown_keys_and_permissions(path):
    path.chmod(0o640)
    set_config_values({"stt.language": "it", "editor": "new"}, path)
    assert load_config(path).stt.language == "it"
    assert load_config(path).editor == "new"
    content = path.read_text()
    assert "# Keep this comment" in content
    assert "# Keep inline" in content
    assert "unknown = 42" in content
    assert path.stat().st_mode & 0o777 == 0o640


def test_reset_and_edit_are_validated_together(path):
    set_config_values({"stt.language": None, "editor": "new"}, path)
    assert load_config(path).stt.language == "auto"
    assert "language =" not in path.read_text()
    assert load_config(path).editor == "new"


def test_failed_replace_retains_original_and_removes_temporary_file(path):
    original = path.read_bytes()
    with patch("dictare.config.os.replace", side_effect=OSError("write failed")), pytest.raises(OSError):
        set_config_values({"editor": "new"}, path)
    assert path.read_bytes() == original
    assert not list(path.parent.glob(".*.tmp"))


def test_symlink_target_is_updated_without_replacing_link(path):
    link = path.parent / "linked.toml"
    link.symlink_to(path)
    set_config_values({"editor": "new"}, link)
    assert link.is_symlink()
    assert load_config(path).editor == "new"


def test_batch_http_validation_is_atomic(path):
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    original = path.read_bytes()
    result = client.post("/api/settings", json={"values": {"editor": "new", "server.port": "invalid"}})
    assert result.status_code == 400
    assert path.read_bytes() == original
    result = client.post("/api/settings", json={"values": {"editor": "new", "stt.language": ""}})
    assert result.status_code == 200
    assert load_config(path).editor == "new"
    assert load_config(path).stt.language == "auto"


@pytest.mark.parametrize("values", [None, {}, [], {"editor": None}, {"editor": {}}])
def test_batch_http_rejects_invalid_shape(path, values):
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    original = path.read_bytes()
    assert client.post("/api/settings", json={"values": values}).status_code == 400
    assert path.read_bytes() == original


def test_nested_form_fields_preserve_raw_comments_and_other_values(path):
    path.write_text('[stt.advanced]\nbeam_size = 7 # keep\nhotwords = "cat"\nfuture = "preserve"\n')
    set_config_values({"stt.advanced.beam_size": "3", "audio.advanced.pre_buffer_ms": "450"}, path)
    assert load_config(path).stt.advanced.beam_size == 3
    assert load_config(path).audio.advanced.pre_buffer_ms == 450
    assert '# keep' in path.read_text()
    assert 'future = "preserve"' in path.read_text()
    assert 'hotwords = "cat"' in path.read_text()
    set_config_values({"stt.advanced.beam_size": None}, path)
    assert load_config(path).stt.advanced.beam_size == 5
    assert 'beam_size =' not in path.read_text()


def test_invalid_nested_field_leaves_all_edits_unchanged(path):
    original = path.read_bytes()
    with pytest.raises(KeyError):
        set_config_values({"editor": "new", "stt.advanced.unknown": "value"}, path)
    assert path.read_bytes() == original


def test_nested_http_settings_are_saved_together(path):
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    response = client.post('/api/settings', json={'values': {'stt.advanced.beam_size': 4, 'audio.advanced.channels': 2}})
    assert response.status_code == 200
    assert load_config(path).stt.advanced.beam_size == 4
    assert load_config(path).audio.advanced.channels == 2


def test_invalid_nested_choice_does_not_save_other_fields(path):
    from pydantic import ValidationError

    original = path.read_bytes()
    with pytest.raises(ValidationError):
        set_config_values({"editor": "new", "stt.advanced.device": "imaginary"}, path)
    assert path.read_bytes() == original
