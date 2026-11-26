# Evolution loop: keeping the test spec, matrix and tests alive

Code, features and rules change every iteration; the test spec must follow. The loop below is run by an agent on
each trigger. It produces **proposals** (a PR) — never silent edits of the spec, and never a lowered bar without the
user's approval.

## Triggers and how to wire them

| Trigger | Wiring (pick what the project has) |
|---|---|
| Every change | Step 2–5 of SKILL.md; `testguard check` in CI on every PR and in a pre-push hook |
| Rule source changed | Same PR as the rule change (the guard fails otherwise) |
| Bug escaped | Whoever fixes the bug runs the escape analysis (failure-patterns.md) |
| Scheduled | A nightly CI job running `testguard drift --json` (uploads the report); or a scheduled agent (e.g. a cron-triggered Claude Code / Codex run) that executes the maintenance pass below |
| Flaky or skipped test | CI reports (skipped ratio warning); treat as a failure |

## Maintenance pass (scheduled, or when asked "update the test spec")

1. **Measure.** Run the full suite as CI does, then `testguard drift --json`. Collect: new rules without tests,
   coverage lost, stale spec paths, check errors and warnings, skipped/flaky tests, allowlist entries whose
   iteration has passed.
2. **Re-derive the facts in the spec from the code**, section by section (test-spec-template.md): layers and
   frameworks actually present, commands that actually work, environments CI actually uses, seed files that exist.
   Any statement the code contradicts is a finding.
3. **Review recent changes.** Since the last pass (git log): new modules, endpoints, processes, migrations, external
   integrations. Each needs a place in the layer table and, if it carries rules, matrix rows.
4. **Review escapes.** Bugs fixed since the last pass: did each get its escape analysis and a test citing its rule?
   Do two or more share a cause? Then propose a principle or failure pattern.
5. **Propose.** One PR containing: the regenerated matrix; spec edits with a "why" for each (drift item, escaped
   bug, changed code); new tests for small gaps; a plan (rule, kinds, layer, owner) for large gaps. Raising a bar
   (a new `require_kinds`, removing an allowlist entry by adding tests) can be done directly; lowering one is listed
   for explicit approval.
6. **Record.** Append a dated line to the spec's change log: what changed, the coverage numbers before and after.

## What the loop must not do

- Delete or weaken a failing test to make the pass green.
- Add allowlist entries to make `check` pass without listing them for approval.
- Rewrite the spec wholesale; change it section by section, each change motivated.
- Copy production or personal data into fixtures.
