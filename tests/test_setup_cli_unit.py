"""First-run setup orchestration without installing services or models."""

from unittest.mock import MagicMock

import pytest
import typer
from typer.testing import CliRunner

from dictare.cli.setup import register


@pytest.fixture
def setup_cli(monkeypatch, tmp_path):
    import dictare.cli.models as models
    import dictare.config as config
    import dictare.daemon.systemd as backend
    app = typer.Typer()
    register(app)
    path = tmp_path / "config.toml"
    create = MagicMock()
    model_check = MagicMock(return_value=True)
    monkeypatch.setattr(config, "get_config_path", lambda: path)
    monkeypatch.setattr(config, "create_default_config", create)
    monkeypatch.setattr(config, "load_config", lambda: "config")
    monkeypatch.setattr(models, "ensure_required_models", model_check)
    monkeypatch.setattr(backend, "is_installed", MagicMock(return_value=False))
    monkeypatch.setattr(backend, "install", MagicMock())
    monkeypatch.setattr(backend, "start", MagicMock())
    monkeypatch.setattr("sys.platform", "linux")
    return app, path, create, model_check, backend


def test_setup_creates_config_and_starts_service(setup_cli):
    app, _, create, check, backend = setup_cli
    result = CliRunner().invoke(app)
    assert result.exit_code == 0, result.output
    create.assert_called_once()
    check.assert_called_once_with("config")
    backend.install.assert_called_once()
    backend.start.assert_called_once()
    assert "Setup complete" in result.output


def test_setup_stops_when_model_download_fails(setup_cli):
    app, path, create, check, backend = setup_cli
    path.write_text("existing")
    check.return_value = False
    result = CliRunner().invoke(app)
    assert result.exit_code == 1
    assert "Model download failed" in result.output
    create.assert_not_called()
    backend.install.assert_not_called()


def test_setup_existing_service_and_install_error(setup_cli):
    app, _, _, _, backend = setup_cli
    backend.is_installed.return_value = True
    result = CliRunner().invoke(app)
    assert result.exit_code == 0
    assert "already installed" in result.output
    backend.install.assert_not_called()
    backend.is_installed.side_effect = OSError("unavailable")
    result = CliRunner().invoke(app)
    assert result.exit_code == 0
    assert "Service install failed" in result.output
