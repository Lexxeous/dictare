# Develop and checkpoint standard

This page is the authoritative workflow for this fork's local feature requests.
Read it with `AGENTS.md` and `CONTRIBUTING.md` before adding or implementing a
request. The integration branch is `develop`.

## Register and implement requests

1. Create or update the ignored local request folder under
   `feature-requests/<trivial|small|medium|large>/<request-name>/` and record
   status, complexity, evidence and next action in the request and roadmap.
2. Develop directly in the main Dictare checkout on `develop`, using its existing
   `./scripts/dev.sh stack` source server. New requests do not require feature
   branches, worktrees, or separate preview servers.
3. Keep unrelated changes separate in focused commits. Inspect status and diff
   before editing; coordinate explicitly if another session owns the same files.
   Preserve existing feature branches/worktrees and their unmerged checkpoints;
   integrate relevant completed work deliberately without resetting them.
4. Continue the documented trivial, small, medium, large order unless the user
   explicitly prioritizes a request. Update local notes with commit and release
   intent as work proceeds.

## Validate and commit checkpoints

At a coherent checkpoint:

1. Inspect the checkout diff and stage only that request's intended files/hunks.
   Add meaningful focused regression tests for changed behavior; follow the
   existing test patterns and mock hardware, services, and provider responses.
2. Run relevant focused tests and lint. Run the repository-wide Python checks
   required by CI before declaring the feature ready for review. UI changes
   require the UI build, review of generated packaged assets, and visual checks
   at desktop/narrow widths. Native integration also requires appropriate
   platform/hardware checks before support is advertised.
3. Review config defaults/migrations, README, Unreleased changelog, CLI help,
   permissions, and any new dependency or platform requirement. Research
   substantial dependency choices using maintained official sources and record
   the decision. Keep credentials and private planning context out of commits.
4. Review local build/runner scripts and workspace master dispatch for every
   feature. Update affected commands, flags, dependency setup, ports, packaging,
   and isolation documentation in the same change. Validate shell syntax and
   dry-run plans; use isolated checks for lifecycle behavior. Record explicitly
   when no script change is needed and why.
5. Record exact commands, results, known failures, remaining acceptance work,
   decisions, commit, and relevant historical branch/worktree in the request and roadmap.
   Missing tools or unavailable hardware are outstanding validation, not passes.
6. When the checkpoint's required checks pass and the staged diff is clean and
   scoped, commit it on develop with a short imperative subject.
   Record the commit in the local notes, verify the scoped changes are committed,
   and continue in size order. Further commits can complete later checkpoints.

Keep **checkpoint committed**, **Ready for review**, and **Released** distinct.
A validated checkpoint is committed directly to develop; do not claim a feature
complete while required acceptance or regression checks remain unresolved.
Select intermittent validated develop batches for main during an explicit
release-preparation task. Publish real releases from main only. Pushing,
opening remote PRs, or publishing still requires the user's authorization.

## Release intent and development versions

- Each feature records its release intent in the local request/register/roadmap.
  Add the matching public `.changes/<request-name>.toml` with its first
  implementation checkpoint: patch for compatible fixes, minor for added
  capabilities, or none for contributor-only work. Never copy private notes.
- Do not reserve a future numeric version per feature. Before push or release,
  refresh the fork's main/develop refs and stable tags and run
  `.venv/bin/python scripts/release_plan.py --main-ref <fork-remote>/main`.
  Record the recalculated target and the baseline ref/commit in local notes.
  CI also recalculates the plan on feature/develop/main pushes and PRs.
- A release batch uses the highest pending intent, with the pending main
  release as a floor. Several fixes in one batch consume one patch version;
  a minor feature promotes that batch to a minor release. A feature completed
  after a completed main release recalculates against that new stable tag.
  Already-released immutable intent records do not bump the next batch.
  After a main release, merge main back into develop before continuing
  development so the released source version, tags, and
  consumed intents become the new baseline.
- The initial selected target is to finish 0.7.0, currently 0.7.0rc2 in source.
  A patch arriving before that release joins 0.7.0. After 0.7.0 is released,
  a patch-only batch targets 0.7.1 and a batch containing a minor feature
  targets 0.8.0. Recompute after any change in release/merge order.
- `--local-version` prints a target-based dev label containing commit distance,
  branch, SHA, and dirty state. Use it for source-build identification; the
  packaged source version remains the literal release version until release
  preparation updates source and changelog together. Do not publish dev labels.
- Release preparation on main must pass `--check-release`, which checks the
  actual source version against the recalculated release line and requires
  its changelog section. The publishing workflow rejects other branches.
  CI checks are evidence only after they actually run remotely; configuring
  required checks/branch protection in GitHub is a separate repository setting.

## Keep documentation current

Update the request README, status register, and roadmap after each material
finding or change, including branch/base/worktree, test evidence, blockers,
decisions, next action, and commits. Place durable repository rules here or in
the relevant existing guide. Put cross-project standards in the workspace
Docs handbook without copying private request details. Update all links when
moving requests, and preserve completed requests with actual release evidence.
