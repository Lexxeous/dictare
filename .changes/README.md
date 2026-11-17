# Release intents

Each implemented feature branch includes `<request-name>.toml`:

```toml
name = "request-name"
bump = "patch"  # patch for compatible fixes; minor for added capabilities
summary = "Short public release description."
```

Use the exact request/branch slug. Do not copy private request notes here or
reserve a fixed version in a feature branch. Create the record with the first
implementation checkpoint; do not merge a planned-only record as a feature.
`none` is available for contributor-only changes with no release impact.

Run `.venv/bin/python scripts/release_plan.py` after refreshing the main release history
and after each merge. The highest pending bump wins within a release batch.
The pending 0.7.0 release remains a floor until it is published. Records already
included unchanged in the latest stable main tag do not bump another release.
Keep records immutable after release; add a new request/record for later work.

The planner is read-only. Main release preparation explicitly updates the
literal source version and changelog after selecting a validated develop batch.
See `.github/feature-workflow.md` for branch and release gates.
