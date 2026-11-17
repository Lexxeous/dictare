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


def test_sound_fields_use_event_defaults_and_preserve_other_events(path):
    path.write_text('[audio.sounds.transcribed]\nvolume = 0.6 # keep\nfuture = "yes"\n[audio.sounds.ready]\nenabled = false\n')
    set_config_values({'audio.sounds.transcribed.volume': '0.4', 'audio.sounds.start.enabled': 'false'}, path)
    assert load_config(path).audio.sounds['transcribed'].volume == 0.4
    assert not load_config(path).audio.sounds['start'].enabled
    assert 'future = "yes"' in path.read_text()
    assert '# keep' in path.read_text()
    assert not load_config(path).audio.sounds['ready'].enabled
    set_config_values({'audio.sounds.transcribed.volume': None, 'audio.sounds.start.enabled': None}, path)
    assert load_config(path).audio.sounds['transcribed'].volume == 1.0
    assert load_config(path).audio.sounds['start'].enabled


def test_sound_invalid_volume_or_unknown_event_is_atomic(path):
    from pydantic import ValidationError

    original = path.read_bytes()
    with pytest.raises(ValidationError):
        set_config_values({'editor': 'new', 'audio.sounds.start.volume': '2'}, path)
    assert path.read_bytes() == original
    with pytest.raises(KeyError):
        set_config_values({'editor': 'new', 'audio.sounds.imaginary.enabled': 'true'}, path)
    assert path.read_bytes() == original


def test_pipeline_scalar_settings_preserve_patterns(path):
    path.write_text('[pipeline.mute_filter]\nenabled = true # keep\nmute_triggers = { "*" = [["hello", "mute"]] }\n')
    set_config_values({'pipeline.mute_filter.enabled': 'false', 'pipeline.agent_filter.match_threshold': '0.7'}, path)
    assert not load_config(path).pipeline.mute_filter.enabled
    assert load_config(path).pipeline.agent_filter.match_threshold == 0.7
    assert 'mute_triggers = { "*" = [["hello", "mute"]] }' in path.read_text()
    assert '# keep' in path.read_text()
    set_config_values({'pipeline.mute_filter.enabled': None}, path)
    assert load_config(path).pipeline.mute_filter.enabled


def test_pipeline_complex_settings_cannot_be_replaced_by_scalar_form(path):
    original = path.read_bytes()
    with pytest.raises(ValueError):
        set_config_values({'pipeline.mute_filter.mute_triggers': 'bad'}, path)
    assert path.read_bytes() == original


def test_agent_default_and_permissions_preserve_profiles(path):
    path.write_text('[agent_profiles]\ndefault = "codex" # keep\n[agent_profiles."my.profile"]\ncommand = ["example"]\nextra = "preserve"\n')
    set_config_values({'agent_profiles.default': 'my.profile', 'agent_profiles.live_dangerously': 'true'}, path)
    config = load_config(path)
    assert config.agent_profiles.default == 'my.profile'
    assert config.agent_profiles.live_dangerously
    assert config.agent_profiles.get('my.profile').command == ['example']
    assert '# keep' in path.read_text()
    assert 'extra = "preserve"' in path.read_text()
    set_config_values({'agent_profiles.default': None}, path)
    assert load_config(path).agent_profiles.default is None


def test_pipeline_string_lists_round_trip_without_rewriting_other_patterns(path):
    path.write_text('[pipeline.agent_filter]\ntriggers = ["agent"] # keep\n[pipeline.mute_filter.mute_triggers]\nes = [["silencio"]]\n')
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    response = client.post('/api/settings', json={'values': {'pipeline.agent_filter.triggers': ['assistant', '', 'agent'], 'pipeline.mute_filter.listen_phrases': []}})
    assert response.status_code == 200
    config = load_config(path)
    assert config.pipeline.agent_filter.triggers == ['assistant', 'agent']
    assert config.pipeline.mute_filter.listen_phrases == []
    assert config.pipeline.mute_filter.mute_triggers['es'] == [['silencio']]
    assert '# keep' in path.read_text()


def test_arbitrary_or_invalid_list_values_are_rejected_atomically(path):
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    original = path.read_bytes()
    for values in ({'editor': ['bad']}, {'pipeline.agent_filter.triggers': [3]}, {'pipeline.mute_filter.mute_triggers': ['bad']}):
        assert client.post('/api/settings', json={'values': values}).status_code in (400, 404)
        assert path.read_bytes() == original


def test_profile_form_updates_exact_name_and_preserves_unknown_values(path):
    path.write_text('[agent_profiles."my.profile"]\ncommand = ["agent"] # keep\nextra = "preserve"\n')
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    response = client.post('/api/settings', json={'values': {'editor': 'new'}, 'profiles': {'my.profile': {'command': ['agent', '--resume'], 'description': 'My agent'}}})
    assert response.status_code == 200
    assert load_config(path).agent_profiles.get('my.profile').command == ['agent', '--resume']
    assert load_config(path).editor == 'new'
    assert '# keep' in path.read_text() and 'extra = "preserve"' in path.read_text()


def test_invalid_profile_update_rejects_whole_batch(path):
    path.write_text('[agent_profiles.codex]\ncommand = ["codex"]\n')
    original = path.read_bytes()
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    for changes in ({'codex': {'command': [3]}}, {'missing': {'description': 'x'}}, {'codex': {'future': 'x'}}):
        response = client.post('/api/settings', json={'values': {'editor': 'new'}, 'profiles': changes})
        assert response.status_code in (400, 404)
        assert path.read_bytes() == original


def test_profile_permission_override_can_be_inherited(path):
    path.write_text('[agent_profiles.codex]\ncommand = ["codex"]\nlive_dangerously = true\n')
    set_config_values({}, path, profile_updates={'codex': {'live_dangerously': None}})
    assert load_config(path).agent_profiles.get('codex').live_dangerously is None
    assert 'live_dangerously' not in path.read_text()


def test_empty_profile_command_is_rejected(path):
    path.write_text('[agent_profiles.codex]\ncommand = ["codex"]\n')
    original = path.read_bytes()
    with pytest.raises(ValueError):
        set_config_values({}, path, profile_updates={'codex': {'command': []}})
    assert path.read_bytes() == original


def test_language_patterns_are_validated_and_saved_without_touching_other_settings(path):
    path.write_text('[pipeline.mute_filter.mute_triggers]\nes = [["vale", "silencio"]] # keep\n')
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    patterns = {'*': [['dictare|okay', 'mute']], 'es': [['vale', 'silencio']]}
    response = client.post('/api/settings', json={'values': {'pipeline.mute_filter.mute_triggers': patterns}})
    assert response.status_code == 200
    assert load_config(path).pipeline.mute_filter.mute_triggers == patterns
    assert '# keep' in path.read_text()


def test_invalid_patterns_and_arbitrary_objects_do_not_partially_save(path):
    original = path.read_bytes()
    client = TestClient(OpenVIPServer(MockEngine(), MockController(), port=0)._app)
    for key, value in [('pipeline.mute_filter.mute_triggers', {'es': ['not a pattern']}), ('editor', {'bad': 'value'})]:
        response = client.post('/api/settings', json={'values': {'editor': 'new', key: value}})
        assert response.status_code in (400, 404)
        assert path.read_bytes() == original


def test_editing_a_language_pattern_keeps_its_inline_comment(path):
    path.write_text('[pipeline.mute_filter.mute_triggers]\nes = [["vale", "silencio"]] # keep\n')
    set_config_values({'pipeline.mute_filter.mute_triggers': {'es': [['vale', 'mudo']]}}, path)
    assert load_config(path).pipeline.mute_filter.mute_triggers['es'] == [['vale', 'mudo']]
    assert '# keep' in path.read_text()
