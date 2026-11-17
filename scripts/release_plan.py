#!/usr/bin/env python3
"""Read-only release planning for this fork's main/develop/feature workflow.

The source version remains the release authority. This helper only plans the
next stable target and a unique local development label; it never edits Git,
versions, tags, or manifests. It supports this project's X.Y.Z release line
with an optional Python a/b/rc/dev suffix, not arbitrary version formats.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    raise SystemExit("Use Python 3.11: .venv/bin/python scripts/release_plan.py") from None

VERSION_PATH = "src/dictare/__init__.py"
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(?:a|b|rc)\d+|\.dev\d+)?$")
STABLE_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def version_core(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Unsupported project version: {value}")
    return int(match[1]), int(match[2]), int(match[3])


def source_version(text: str) -> str:
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                version_core(node.value.value)
                return node.value.value
    raise ValueError("Missing literal __version__ assignment")


def choose_target(released: str, declared: str, bumps: list[str]) -> str:
    """Aggregate one release batch; adding several fixes does not reserve numbers."""
    if any(bump not in {"none", "patch", "minor"} for bump in bumps):
        raise ValueError("Release intent must be none, patch, or minor")
    major, minor, patch = version_core(released)
    candidate = (major, minor, patch)
    if "minor" in bumps:
        candidate = (major, minor + 1, 0)
    elif "patch" in bumps:
        candidate = (major, minor, patch + 1)
    target = max(candidate, version_core(declared))
    return ".".join(str(part) for part in target)


def read_intent(path: Path) -> dict[str, str]:
    data = tomllib.loads(path.read_text())
    name, bump, summary = data.get("name"), data.get("bump"), data.get("summary")
    if name != path.stem or not SLUG_PATTERN.fullmatch(str(name)):
        raise ValueError(f"Intent name must match its request filename: {path}")
    if bump not in {"none", "patch", "minor"} or not isinstance(summary, str) or not summary.strip():
        raise ValueError(f"Invalid release intent: {path}")
    return {"name": name, "bump": bump, "summary": summary}


def plan(root: Path, main_ref: str = "main", branch: str | None = None) -> dict:
    """Use only stable tags reachable from main and not-yet-released intents."""
    tags = git(root, "tag", "--merged", main_ref).splitlines()
    stable = [(version_core(tag[1:]), tag) for tag in tags if STABLE_TAG_PATTERN.fullmatch(tag)]
    if not stable:
        raise ValueError("No stable vX.Y.Z tag reachable from main; fetch release history first")
    released_core, released_tag = max(stable)
    released = ".".join(str(part) for part in released_core)
    try:
        git(root, "merge-base", "--is-ancestor", released_tag, "HEAD")
    except subprocess.CalledProcessError as error:
        raise ValueError("Branch predates the latest main release; sync develop before pushing") from error
    declared = source_version(git(root, "show", f"{main_ref}:{VERSION_PATH}"))
    branch = branch or git(root, "branch", "--show-current")
    intents = []
    directory = root / ".changes"
    for path in sorted(directory.glob("*.toml")):
        intent = read_intent(path)
        # Unchanged records already present in the last stable release are spent.
        try:
            previous = git(root, "show", f"{released_tag}:.changes/{path.name}")
        except subprocess.CalledProcessError:
            previous = None
        if previous != path.read_text().strip():
            intents.append(intent)
    if branch.startswith("feature/"):
        slug = branch.removeprefix("feature/")
        if not SLUG_PATTERN.fullmatch(slug):
            raise ValueError("Feature branch must use feature/<request-name>")
        if not any(intent["name"] == slug for intent in intents):
            raise ValueError(f"Missing unreleased .changes/{slug}.toml for {branch}")
    target = choose_target(released, declared, [intent["bump"] for intent in intents])
    distance = int(git(root, "rev-list", "--count", f"{released_tag}..HEAD"))
    revision = git(root, "rev-parse", "--short", "HEAD")
    label = re.sub(r"[^a-z0-9]+", ".", branch.lower()).strip(".") or "detached"
    dirty = bool(git(root, "status", "--porcelain", "--untracked-files=normal"))
    local = f"{target}.dev{distance}+{label}.g{revision}" + (".dirty" if dirty else "")
    return {
        "branch": branch,
        "main_ref": main_ref,
        "latest_stable": released_tag,
        "declared_main_version": declared,
        "target_release": target,
        "local_version": local,
        "intents": intents,
        "dirty": dirty,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-ref", default="main", help="Fresh main ref (e.g. forked/main before push)")
    parser.add_argument("--branch", help="Branch name for detached CI checkouts")
    parser.add_argument("--local-version", action="store_true", help="Print only the development label")
    parser.add_argument("--check-release", action="store_true", help="Validate release source and changelog on main")
    args = parser.parse_args()
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
    try:
        result = plan(root, args.main_ref, args.branch)
        if args.check_release:
            if result["branch"] != "main":
                raise ValueError("Releases may only be prepared/published from main")
            version = source_version((root / VERSION_PATH).read_text())
            if ".dev" in version or version_core(version) != version_core(result["target_release"]):
                raise ValueError(f"Set the main release version to {result['target_release']} during release preparation")
            if f"## [{version}]" not in (root / "CHANGELOG.md").read_text():
                raise ValueError(f"Missing CHANGELOG section for {version}")
        print(result["local_version"] if args.local_version else json.dumps(result, indent=2))
    except (ValueError, subprocess.CalledProcessError, OSError, tomllib.TOMLDecodeError) as error:
        parser.exit(1, f"Release plan failed: {error}\n")


if __name__ == "__main__":
    main()
