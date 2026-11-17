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
- Put common contributor infrastructure in a separate prerequisite branch.
  Record its commit when using it as the shared base. Newly created branches
  may advance to that common base only after verifying they have no work of
  their own; never reset an existing implementation to do so.

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
**Released** distinct. Only claim each when its evidence exists. Do not bump
the version for an ordinary contribution; maintainers coordinate releases.
Pushing, opening a PR, merging, and publishing require the user's separate
authorization. This workflow authorizes local request branch creation and
validated checkpoint commits during requested feature implementation.

## Keep documentation current

Update the request README, status register, and roadmap after each material
finding or change, including branch/base/worktree, test evidence, blockers,
decisions, next action, and commits. Place durable repository rules here or in
the relevant existing guide. Put cross-project standards in the workspace
Docs handbook without copying private request details. Update all links when
moving requests, and preserve completed requests with actual release evidence.
