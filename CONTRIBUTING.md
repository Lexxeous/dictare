# Contributing to Dictare

Thank you for helping improve Dictare. This guide covers the public
contribution path. For module boundaries and coding-agent instructions, see
[AGENTS.md](AGENTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

## Development Setup

Dictare currently targets Python 3.11.

```bash
git clone https://github.com/dragfly/dictare.git
cd dictare
uv sync --python 3.11 --extra dev
uv run --python 3.11 dictare --help
```

For a checkout-local environment that stays separate from an installed
Homebrew version, use `./scripts/dev.sh setup`, then
`./scripts/dev.sh run --help` or `./scripts/dev.sh stack`. The local runner
uses `.venv` and stores its copied config, PID, logs, stats, and session data
under the ignored `.dictare-dev/` directory. It uses engine port 18770 and UI
port 5173; it does not run service lifecycle commands. See
`./scripts/dev.sh --help` for the full command list.

Open `http://127.0.0.1:5173/ui/` for local settings. Use
`./scripts/dev.sh listen` and `./scripts/dev.sh pause` in another terminal for
capture control. Global hotkey handling is disabled in this local runner;
native launcher/hotkey changes need their own platform-specific check.

On Apple Silicon, add `--extra mlx` if you need the MLX speech stack. UI work
also requires pnpm dependencies in `ui/`.

## Tests and Checks

Run the focused tests for your change, then the checks used by CI:

```bash
uv run --python 3.11 pytest tests/ -x --tb=short
uv run --python 3.11 ruff check src/ tests/
uv run --python 3.11 mypy src/
uv run --python 3.11 bandit -r src/ -lll -q
```

The CI workflow also runs the full test suite under Xvfb with coverage. For
settings UI changes, edit `ui/src/`, build the UI, and review the generated
changes in `src/dictare/ui/dist/`:

```bash
cd ui
pnpm install --frozen-lockfile
pnpm build
```

## Scope and Branches

For this fork's local request register, follow the
[feature branch and checkpoint standard](.github/feature-workflow.md): create
`feature/<request-name>` immediately when a request is added, using the exact
request folder name. Record its base and branch in the request notes and
roadmap. Implement trivial requests before small, then medium, then large;
validate and commit scoped checkpoints on isolated feature branches. Review
build/runner scripts with each feature and keep commands/documentation current.
These fork-specific rules take precedence over the general naming examples
below when working from the local feature-request register.

- Start from the target branch named by the issue or maintainer. If none is
  specified for an upstream contribution, check the repository's current
  default branch before creating a topic branch.
- Use one branch and pull request per independently reviewable change. Common
  prefixes are `feature/`, `fix/`, `docs/`, and `test/`; keep the suffix short
  and descriptive, such as `fix/codex-resume-session`.
- Do not combine unrelated features just because they affect the same area.
  If one change depends on another, describe the dependency in the pull
  request. Otherwise, base both branches on the target branch and merge them
  independently.
- Keep commits focused. Conventional prefixes such as `feat:`, `fix:`,
  `docs:`, `test:`, `refactor:`, and `chore:` are used in the existing history.

For local work in a personal fork, follow the fork's integration-branch policy.
The repository-specific agent guide describes the `develop`-based workflow used
for this checkout.

Feature branches start from `develop` and merge back after validation. Main
receives selected validated develop batches and is the release branch. Track
patch/minor intent in a public `.changes/<request-name>.toml` with each
implementation; recalculate its target using `scripts/release_plan.py` against
fresh main refs/tags before pushing or merging. Fixed future versions in
feature branches become stale when merge order changes. The initial pending
release is 0.7.0; later targets follow the latest main stable release and the
highest intent in the batch. See the feature workflow for exact gates.

## Code and Documentation

- Follow existing patterns and module boundaries. Add type hints to new Python
  functions and tests for new behavior or bug fixes.
- Keep settings schema, defaults, migrations, and UI behavior consistent.
- Update README or other user docs when a command or user-visible behavior
  changes.
- Add user-visible changes under the `[Unreleased]` heading in
  `CHANGELOG.md`. Use present-tense entries, such as “Show the resumed Codex
  session ID.”
- Do not bump `src/dictare/__init__.py` for an ordinary feature or fix. Version
  bumps and release notes are coordinated by maintainers as part of a release.

## Pull Requests

Before opening a pull request:

1. Run relevant tests and checks, and report the exact commands and results.
2. Summarize the user problem and the behavior change.
3. Explain any compatibility, configuration, or migration impact.
4. Link related issues and keep unrelated work out of the branch.

Fill out the pull request template. Expect CI and maintainer review before
merge; respond to review comments with focused commits.

## Release Cycle

The package version is maintained in `src/dictare/__init__.py`. The release
workflow `.github/workflows/publish-pypi.yml` is manually dispatched by
maintainers after a release version and changelog section are prepared. It
publishes to PyPI; stable versions also receive a GitHub release/tag and a
Homebrew tap update, while prereleases publish to PyPI only. Contributors
should leave release tagging and publishing to maintainers.

## Reporting Issues

Use the GitHub issue templates for bugs and feature requests. Include the
Dictare version, operating system, Python version, installation method, exact
steps to reproduce, expected behavior, and relevant sanitized logs. Do not
attach credentials or private operational data.

Please also read the [Code of Conduct](CODE_OF_CONDUCT.md) and
[Security Policy](SECURITY.md). Report security vulnerabilities using the
process in `SECURITY.md`, not a public issue.
