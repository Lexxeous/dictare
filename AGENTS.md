# Repository Guide for Coding Agents

Read this file before changing Dictare. `CONTRIBUTING.md` describes the public
contribution flow, and `ARCHITECTURE.md` describes the runtime and module
boundaries. Keep those documents aligned with the implementation.

## Project Shape

- Python 3.11 package: `src/dictare/`; CLI commands are registered in
  `src/dictare/cli/` with Typer.
- Agent launch and session continuity: `src/dictare/agent/`. Keep commands as
  argument lists; do not build shell command strings.
- Runtime engine and HTTP/OpenVIP routes: `src/dictare/core/` and
  `src/dictare/app/`.
- Settings UI source: `ui/src/` (SvelteKit/Svelte 5). The packaged UI is built
  into `src/dictare/ui/dist/`; edit the source and regenerate the packaged
  output when changing the UI.
- Tests live in `tests/` and generally mirror the source module they cover.
- Configuration models, defaults, and migration behavior live in
  `src/dictare/config.py`.

## Implementation Standards

- Follow the existing module and registration patterns. Add CLI options to the
  Typer command signature so they appear in `--help`; keep `ctx.args` parsing
  only for arguments intentionally forwarded to child agent commands.
- Treat agent CLIs and their local session formats as changing external
  interfaces. Adapters should fail safely and retain the documented fallback.
- Keep Dictare's session registry a pointer to the agent's own session store;
  never replace or rewrite agent-owned session history.
- Keep changes scoped to one behavior. Add focused tests for new behavior and
  regressions, and update README/CHANGELOG where a user-visible command or
  behavior changes.
- Use the current configuration model and TOML helpers instead of introducing
  a second configuration path. Preserve unknown user settings and comments
  where existing TOML editing code does so.
- Save related ordinary form fields through the validated settings batch API.
  It validates all form values before one comment-preserving file replacement.
  TOML sections, model operations, and shortcuts are separate save steps.
- Phrase controls reuse the pipeline tokenizer and matching rules. Preserve
  advanced language patterns when offering normal fields, validate conflicting
  actions together, and display effective saved defaults rather than the
  generic schema's intentionally blank unset string fields. Do not expose
  unrelated configuration values in validation errors.
- Keep capture lifetime separate from recognition-worker recovery. Carry capture
  identity through VAD/jobs/completions/timeouts and check it before side effects.
  Reset VAD before advancing capture generation; never acquire the delivery lock
  from a VAD callback holding the VAD lock. See ARCHITECTURE.md for ownership.
- Do not add dependencies for a small local change. For substantial new
  functionality, review existing project code and maintained library options,
  then record any material adoption decision in the appropriate documentation.
- Do not run route-changing, service-changing, or microphone actions as tests
  unless the change explicitly requires that live behavior. Prefer mocks and
  isolated temporary paths.
- Keep credentials, tokens, private keys, and personal operational data out of
  source, tests, examples, and tracked documentation.

## Development Checks

`./scripts/dev.sh setup` installs the local environment; add `--mlx` for the
Apple Silicon speech extra. `./scripts/dev.sh stack` runs the local engine and
UI with ignored `.dictare-dev/` state and alternate ports. Use `listen` and
`pause` for capture control; global hotkeys are disabled in source mode.
`test`, `lint`, and `typecheck` use the same checkout-local Python environment.

Use the repository's Python 3.11 environment:

```bash
uv run --python 3.11 pytest tests/ -x --tb=short
uv run --python 3.11 ruff check src/ tests/
uv run --python 3.11 mypy src/
```

The CI workflow also runs Bandit and the full test suite with coverage. For UI
changes, run the UI build from `ui/` and inspect the resulting diff in
`src/dictare/ui/dist/`.

## Branches and Release Notes

Follow [.github/feature-workflow.md](.github/feature-workflow.md) as the
authoritative request/branch/checkpoint workflow.

- Immediately create `feature/<request-name>` from the committed `develop`
  base when adding a request. Use its full folder name, record branch/base in
  the request README, root register, and roadmap, and never overwrite an
  existing branch. Do not switch a dirty checkout to register a request.
- Implement in order: trivial, small, medium, large. Use isolated worktrees,
  meaningful focused tests, and validated scoped checkpoint commits before
  advancing. Record blockers and ask when a required check or decision cannot
  be resolved. Do not bundle unrelated work or stack independent branches.
- Review local and workspace build/runner scripts at each feature checkpoint;
  update them with changed commands, dependencies, packaging, or behavior and
  record validation. Keep findings and statuses current in the local notes.
- Keep each branch and pull request limited to one independently reviewable
  outcome. Do not bring unrelated local feature requests into a code change.
- Put user-visible unreleased changes under `[Unreleased]` in `CHANGELOG.md`.
  Do not bump the package version for an ordinary contribution. Release
  versions and publishing are maintainer actions handled by the workflow in
  `.github/workflows/publish-pypi.yml`.
- Do not push, open a pull request, merge, or create a release unless the user
  asks for that action.

The standing feature workflow now permits merging validated implementations
back into develop during requested feature work. All feature branches start
from develop; main is reserved for selected release batches. Before push/merge,
refresh release refs/tags and recalculate patch/minor intent using
`scripts/release_plan.py`; keep local request/register/roadmap targets current.
Publishing and remote pushes/PRs still require explicit authorization. Follow
the detailed workflow for intent records, local dev labels, and main release gates.

## Private Local Feature Requests

`feature-requests/` is ignored by Git on purpose. Put each independent request
under `feature-requests/<complexity>/<request-name>/`, using exactly the
`trivial`, `small`, `medium`, and `large` complexity groups. Size implementation
and validation scope, not priority or completion status. Each request README
records its current status, sizing rationale, review date, branch, next action,
user problem, verified source findings, and acceptance criteria.

Keep the root feature-request `README.md` and `IMPLEMENTATION-ROADMAP.md` as
running documentation. Whenever scope, complexity, status, implementation,
validation, dependencies, branch/PR, or release evidence changes, update both
files and the affected request README in the same task. Record meaningful
decisions/status changes in the roadmap history and update the review dates.
Keep current tables accurate; retain completed requests with release evidence
when available. Follow the status definitions in the root request README, and
do not mark code ready or released while required checks remain incomplete.

If complexity changes, move the complete request folder and repair all links.
These notes remain local context; do not force-add or copy them into a commit
unless the user explicitly asks to publish them.

Give request folders to independently implementable features or fixes. Place
inherited project context directly in the relevant request or existing guide;
keep shared planning decisions in the roadmap instead of creating a migration
feature folder.
