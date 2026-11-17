"""Release batches must remain correct when feature merge order changes."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "release_plan", Path(__file__).parents[1] / "scripts" / "release_plan.py"
)
assert _spec and _spec.loader
release_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_plan)


@pytest.mark.parametrize(
    ("released", "declared", "bumps", "expected"),
    [
        ("0.6.2", "0.7.0rc2", ["patch"], "0.7.0"),
        ("0.6.2", "0.7.0rc2", ["minor", "patch"], "0.7.0"),
        ("0.6.2", "0.7.0rc2", ["patch", "minor"], "0.7.0"),
        ("0.7.0", "0.7.0", ["patch", "patch"], "0.7.1"),
        ("0.7.0", "0.7.0", ["patch", "minor"], "0.8.0"),
        ("0.7.1", "0.7.1", ["minor"], "0.8.0"),
        ("0.8.0", "0.8.0", ["patch"], "0.8.1"),
        ("0.8.0", "0.8.0", ["none"], "0.8.0"),
    ],
)
def test_release_batch_uses_current_release_and_highest_intent(released, declared, bumps, expected):
    assert release_plan.choose_target(released, declared, bumps) == expected


def commit(root, message):
    release_plan.git(root, "add", ".")
    release_plan.git(root, "commit", "-m", message)


def intent(root, name, bump="patch"):
    directory = root / ".changes"
    directory.mkdir(exist_ok=True)
    (directory / f"{name}.toml").write_text(
        f'name = "{name}"\nbump = "{bump}"\nsummary = "Public summary"\n'
    )


@pytest.fixture
def repo(tmp_path):
    release_plan.git(tmp_path, "init", "-b", "main")
    release_plan.git(tmp_path, "config", "user.name", "Test")
    release_plan.git(tmp_path, "config", "user.email", "test@example.invalid")
    version = tmp_path / release_plan.VERSION_PATH
    version.parent.mkdir(parents=True)
    version.write_text('__version__ = "0.6.2"\n')
    commit(tmp_path, "Stable baseline")
    release_plan.git(tmp_path, "tag", "v0.6.2")
    return tmp_path


def test_pending_release_is_not_reserved_per_feature(repo):
    (repo / release_plan.VERSION_PATH).write_text('__version__ = "0.7.0rc2"\n')
    commit(repo, "Existing pending minor")
    release_plan.git(repo, "switch", "-c", "develop")
    release_plan.git(repo, "switch", "-c", "feature/first-fix")
    intent(repo, "first-fix")
    commit(repo, "First fix")
    result = release_plan.plan(repo)
    assert result["target_release"] == "0.7.0"
    assert result["local_version"].startswith("0.7.0.dev2+feature.first.fix.g")
    assert not result["dirty"]


def test_already_released_records_do_not_increment_another_release(repo):
    intent(repo, "first-fix")
    (repo / release_plan.VERSION_PATH).write_text('__version__ = "0.7.0"\n')
    commit(repo, "Release first fix")
    release_plan.git(repo, "tag", "v0.7.0")
    release_plan.git(repo, "switch", "-c", "feature/second-fix")
    intent(repo, "second-fix")
    commit(repo, "Second fix")
    result = release_plan.plan(repo)
    assert result["target_release"] == "0.7.1"
    assert [record["name"] for record in result["intents"]] == ["second-fix"]


def test_stale_feature_must_sync_after_main_release(repo):
    release_plan.git(repo, "branch", "feature/older-feature")
    (repo / release_plan.VERSION_PATH).write_text('__version__ = "0.7.0"\n')
    commit(repo, "Release on main")
    release_plan.git(repo, "tag", "v0.7.0")
    release_plan.git(repo, "switch", "feature/older-feature")
    intent(repo, "older-feature", "minor")
    with pytest.raises(ValueError, match="sync develop"):
        release_plan.plan(repo)


def test_feature_requires_matching_intent(repo):
    release_plan.git(repo, "switch", "-c", "feature/missing-intent")
    with pytest.raises(ValueError, match="Missing unreleased"):
        release_plan.plan(repo)


def test_feature_tags_do_not_become_main_release_baseline(repo):
    release_plan.git(repo, "switch", "-c", "feature/example")
    intent(repo, "example")
    commit(repo, "Example")
    release_plan.git(repo, "tag", "v99.0.0")
    assert release_plan.plan(repo)["latest_stable"] == "v0.6.2"


def test_planner_does_not_mutate_repository(repo):
    before = release_plan.git(repo, "status", "--porcelain")
    head = release_plan.git(repo, "rev-parse", "HEAD")
    release_plan.plan(repo)
    assert release_plan.git(repo, "status", "--porcelain") == before
    assert release_plan.git(repo, "rev-parse", "HEAD") == head


@pytest.mark.parametrize(
    ("mode", "label", "expected"),
    [
        ("1", "0.7.0.dev3+feature.example.gabc123", "0.7.0.dev3+feature.example.gabc123"),
        ("0", "0.7.0.dev3+feature.example.gabc123", "0.7.0rc2"),
        ("1", "not-a-version", "0.7.0rc2"),
    ],
)
def test_local_version_label_requires_explicit_source_mode(mode, label, expected):
    root = Path(__file__).parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / "src"), DICTARE_DEV_MODE=mode, DICTARE_DEV_VERSION=label)
    result = subprocess.check_output(
        [sys.executable, "-c", "import dictare; print(dictare.__version__)"],
        cwd=root,
        env=env,
        text=True,
    )
    assert result.strip() == expected
