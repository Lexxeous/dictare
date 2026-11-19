"""Isolated coverage of model and capability API decisions."""

import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dictare.core.http_routes_models import register_models_routes


@pytest.fixture
def model_api(monkeypatch):
    registry = {
        "whisper-tiny": {"type": "stt", "description": "Tiny", "size_gb": 1,
                         "repo": "example/tiny"},
        "voice": {"type": "tts", "description": "Voice", "size_gb": 2,
                  "repo": "example/voice", "venv": "voice-env", "check_file": "voice.bin"},
        "builtin": {"type": "tts", "description": "Built in", "size_gb": 0,
                    "builtin": True},
        "unknown-type": {"type": "other", "description": "Other", "size_gb": 0},
    }
    monkeypatch.setattr("dictare.cli.models._get_model_registry", lambda: registry)
    monkeypatch.setattr("dictare.cli.models._get_configured_models", lambda config: {"whisper-tiny": "active"})
    monkeypatch.setattr("dictare.config.load_config", lambda: object())
    monkeypatch.setattr("dictare.utils.hf_download.is_repo_cached", lambda repo, check_file: repo == "example/tiny")
    monkeypatch.setattr("dictare.utils.hf_download.get_cache_size", lambda repo: 123)
    monkeypatch.setattr("dictare.tts.venv.is_venv_installed", lambda name: False)
    server = SimpleNamespace(download_jobs={}, run_model_download=Mock(),
                             run_tts_install=Mock(), run_capability_install=Mock())
    app = FastAPI()
    register_models_routes(app, server)
    return TestClient(app), server, registry


def test_model_list_reports_cache_configuration_and_download(model_api):
    client, server, _ = model_api
    server.download_jobs["voice"] = {"status": "downloading", "fraction": 0.5,
                                     "downloaded_bytes": 20, "total_bytes": 40}
    models = {m["id"]: m for m in client.get("/api/models").json()["models"]}
    assert set(models) == {"whisper-tiny", "voice"}
    assert models["whisper-tiny"]["cached"] is True
    assert models["whisper-tiny"]["cache_size_bytes"] == 123
    assert models["whisper-tiny"]["configured"] == "active"
    assert models["voice"]["downloading"] is True
    assert models["voice"]["download_fraction"] == 0.5
    assert models["voice"]["downloaded_bytes"] == 20


def test_model_pull_handles_unknown_cached_and_existing_job(model_api):
    client, server, _ = model_api
    assert client.post("/api/models/missing/pull").status_code == 404
    assert client.post("/api/models/whisper-tiny/pull").json() == {"status": "cached"}
    server.download_jobs["voice"] = {"status": "downloading"}
    assert client.post("/api/models/voice/pull").json() == {"status": "downloading"}


def test_install_starts_background_jobs_once(model_api, monkeypatch):
    client, server, _ = model_api
    thread = Mock()
    factory = Mock(return_value=thread)
    monkeypatch.setattr("dictare.core.http_routes_models.threading", SimpleNamespace(Thread=factory))
    assert client.post("/api/models/voice/pull").json() == {"status": "started"}
    assert factory.call_args.kwargs["target"] is server.run_model_download
    assert client.post("/api/capabilities/voice/install").json() == {"status": "started"}
    assert factory.call_args.kwargs["target"] is server.run_capability_install
    assert thread.start.call_count == 2


def test_capability_readiness_and_existing_install(model_api):
    client, server, _ = model_api
    server.download_jobs["tts-install-voice-env"] = {"status": "downloading", "fraction": 0.25}
    capabilities = {c["id"]: c for c in client.get("/api/capabilities").json()["capabilities"]}
    assert capabilities["whisper-tiny"]["ready"] is True
    assert capabilities["whisper-tiny"]["configured"] is True
    assert capabilities["voice"]["ready"] is False
    assert capabilities["voice"]["venv_installed"] is False
    assert capabilities["voice"]["model_cached"] is False
    assert capabilities["voice"]["download_fraction"] == 0.25
    server.download_jobs["voice"] = {"status": "downloading"}
    assert client.post("/api/capabilities/voice/install").json() == {"status": "installing"}


@pytest.mark.parametrize(("path", "status"), [
    ("missing", 404), ("builtin", 400),
])
def test_capability_install_rejects_invalid_requests(model_api, path, status):
    client, _, _ = model_api
    assert client.post(f"/api/capabilities/{path}/install").status_code == status


def test_capability_install_recognizes_ready_model(model_api):
    client, _, _ = model_api
    assert client.post("/api/capabilities/whisper-tiny/install").json() == {"status": "ready"}


def test_capability_uninstall_only_removes_selected_resources(model_api, monkeypatch, tmp_path):
    client, _, _ = model_api
    cache = tmp_path / "voice"
    cache.mkdir()
    (cache / "weights").write_text("fake")
    removed = Mock()
    monkeypatch.setattr("dictare.tts.venv.VENV_ENGINES", {"voice-env": {}})
    monkeypatch.setattr("dictare.tts.venv.uninstall_venv", removed)
    monkeypatch.setattr("dictare.utils.hf_download.get_hf_cache_dir", lambda repo: cache)
    assert client.delete("/api/capabilities/missing/install").status_code == 404
    assert client.delete("/api/capabilities/builtin/install").status_code == 400
    assert client.delete("/api/capabilities/unknown-type/install").status_code == 400
    assert client.delete("/api/capabilities/voice/install").json() == {"status": "ok"}
    removed.assert_called_once_with("voice-env")
    assert not cache.exists()


@pytest.mark.parametrize(("capability", "key", "value"), [
    ("whisper-tiny", "stt.model", "tiny"), ("voice", "tts.engine", "voice-env"),
])
def test_capability_selection_updates_correct_setting(model_api, monkeypatch, capability, key, value):
    client, _, _ = model_api
    save = Mock()
    monkeypatch.setattr("dictare.config.set_config_value", save)
    assert client.post(f"/api/capabilities/{capability}/select").json() == {
        "status": "ok", "restart_required": True,
    }
    save.assert_called_once_with(key, value)


def test_capability_selection_reports_invalid_config(model_api, monkeypatch):
    client, _, _ = model_api
    assert client.post("/api/capabilities/missing/select").status_code == 404
    assert client.post("/api/capabilities/unknown-type/select").status_code == 400
    monkeypatch.setattr("dictare.config.set_config_value", Mock(side_effect=ValueError("invalid value")))
    response = client.post("/api/capabilities/voice/select")
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid value"


def test_legacy_tts_install_and_uninstall(model_api, monkeypatch):
    client, server, _ = model_api
    monkeypatch.setattr("dictare.tts.venv.VENV_ENGINES", {"voice-env": {}})
    uninstall = Mock()
    monkeypatch.setattr("dictare.tts.venv.uninstall_venv", uninstall)
    factory = Mock(return_value=Mock())
    monkeypatch.setattr("dictare.core.http_routes_models.threading", SimpleNamespace(Thread=factory))
    assert client.post("/api/tts-engines/missing/install").status_code == 404
    assert client.delete("/api/tts-engines/missing/install").status_code == 404
    server.download_jobs["tts-install-voice-env"] = {"status": "downloading"}
    assert client.post("/api/tts-engines/voice-env/install").json() == {"status": "installing"}
    server.download_jobs.clear()
    assert client.post("/api/tts-engines/voice-env/install").json() == {"status": "started"}
    assert factory.call_args.kwargs["target"] is server.run_tts_install
    factory.return_value.start.assert_called_once()
    assert client.delete("/api/tts-engines/voice-env/install").json() == {"status": "ok"}
    uninstall.assert_called_once_with("voice-env")


def test_progress_stream_sends_snapshot_and_removes_listener():
    server = SimpleNamespace(download_jobs={"voice": {"status": "downloading", "fraction": 0.5}},
                             progress_queues=[], progress_queues_lock=threading.Lock())
    app = FastAPI()
    register_models_routes(app, server)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/api/models/pull-progress")

    async def exercise():
        request = SimpleNamespace(is_disconnected=Mock(return_value=None))

        async def connected():
            return False

        request.is_disconnected = connected
        response = await endpoint(request)
        assert len(server.progress_queues) == 1
        event = await anext(response.body_iterator)
        assert json.loads(event["data"]) == {"model_id": "voice", "status": "downloading", "fraction": 0.5}
        await response.body_iterator.aclose()
        assert server.progress_queues == []

    asyncio.run(exercise())
