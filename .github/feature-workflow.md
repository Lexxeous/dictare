# Feature branch and checkpoint standard

This page is the authoritative workflow for this fork's local feature requests.
Read it with `AGENTS.md` and `CONTRIBUTING.md` before adding or implementing a
request. The integration branch is `develop`.

## Register a request immediately

1. Create its local folder at
   `feature-requests/<trivial|small|medium|large>/<request-name>/`.
2. Immediately create `feature/<request-name>` from the current committed
   `develop` base. Use the complete request folder name, without the complexity
   segment. This applies to fixes and documentation requests in this register
   as well as new functionality. A later complexity change does not rename
   the branch.
3. Create the branch reference without switching a dirty checkout. Check for
   an existing matching branch first; do not reset, overwrite, or repurpose it.
4. Record the exact branch name, base commit, complexity, status, next action,
   and eventual worktree path in the request README, root request README, and
   implementation roadmap. Update them in the same task. The local notes stay
   Git-ignored, including after implementation or release.

## Isolate implementation

- Use one feature branch and one independently reviewable PR per request.
  Preserve other sessions' and the user's working changes. Prefer a separate
  worktree for each implementation; do not copy the whole dirty checkout into
  a feature branch.
- Implement in complexity order: **trivial, small, medium, large**. The local
  roadmap records the order within each group. Begin the next feature after
  the current checkpoint passes its checks and is committed. If a required
  check or decision blocks progress, record the blocker and ask the user;
  administrative branch creation can continue without claiming implementation.
- Independent features share the committed integration base. Do not stack
  unrelated feature branches. A real dependency requires a documented base
  and explicit plan; no automatic merging or cherry-picking of unrelated work.
- Develop common contributor infrastructure separately, validate it, and
  integrate it into develop before using it as a shared feature prerequisite.
  Every feature branch must be based on develop. Refresh existing feature
  branches from develop safely; never reset an implementation to a new base.

## Validate and commit checkpoints

At a coherent checkpoint:

1. Inspect the branch diff and stage only that request's intended files/hunks.
   Add meaningful focused regression tests for changed behavior; follow the
   existing test patterns and mock hardware, services, and provider responses.
2. Run relevant focused tests and lint. Run the repository-wide Python checks
   required by CI before declaring the branch ready for review. UI changes
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
   decisions, base commit, and branch/worktree in the request and roadmap.
   Missing tools or unavailable hardware are outstanding validation, not passes.
6. When the checkpoint's required checks pass and the staged diff is clean and
   scoped, commit it on its feature branch with a short imperative subject.
   Record the commit in the local notes, verify the worktree is clean, and
   continue in size order. Further commits can complete later checkpoints.

Keep **checkpoint committed**, **Ready for review**, **merged**, and
**Released** distinct. Only claim each when its evidence exists. Merge a
validated feature into develop as part of the requested implementation flow;
do not merge while required acceptance or regression checks are unresolved.
Select intermittent validated develop batches for main during an explicit
release-preparation task. Publish real releases from main only. Pushing,
opening remote PRs, or publishing still requires the user's authorization.

## Release intent and development versions

- Each feature records its release intent in the local request/register/roadmap.
  Add the matching public `.changes/<request-name>.toml` with its first
  implementation checkpoint: patch for compatible fixes, minor for added
  capabilities, or none for contributor-only work. Never copy private notes.
- Do not reserve a future numeric version per feature. Before push/merge,
  refresh the fork's main/develop refs and stable tags, sync the feature with
  develop, and run `.venv/bin/python scripts/release_plan.py --main-ref <fork-remote>/main`.
  Record the recalculated target and the baseline ref/commit in local notes.
  CI also recalculates the plan on feature/develop/main pushes and PRs.
- A release batch uses the highest pending intent, with the pending main
  release as a floor. Several fixes in one batch consume one patch version;
  a minor feature promotes that batch to a minor release. A feature merged
  after a completed main release recalculates against that new stable tag.
  Already-released immutable intent records do not bump the next batch.
  After a main release, merge main back into develop before creating or
  refreshing feature branches so the released source version, tags, and
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
