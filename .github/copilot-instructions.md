# Copilot Instructions

Before making changes, read the repository's [agent guide](../AGENTS.md),
[architecture](../ARCHITECTURE.md), and [contribution guide](../CONTRIBUTING.md).
Follow the existing module boundaries, Python 3.11 baseline, test patterns, and
release-note rules. Keep each change focused, add regression tests for bug fixes,
and avoid editing generated UI output directly; rebuild it from `ui/` after UI
source changes.

Do not include the ignored `feature-requests/` folder in commits. It contains
local planning notes only.

Follow [the feature workflow](feature-workflow.md): immediately register a
matching `feature/<request-name>` branch for each new local request; implement
in complexity order on isolated branches/worktrees, validate and commit scoped
checkpoints, review runner/build compatibility, and update request/status docs.
