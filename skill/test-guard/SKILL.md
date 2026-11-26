---
name: test-guard
description: Load before writing or changing code or tests, before planning an iteration, after a bug escapes to main or production, and on every scheduled test-maintenance run. Finds the project's test spec and rule coverage matrix (or generates them when the project has none), derives the test cases a change needs from the rules it touches, designs test data that proves those rules, runs the project's test guard, and keeps the spec, the matrix and the tests evolving with the code. Tool-agnostic: the same files work for Claude Code, Codex and other agents.
---

# Test guard

Tests rot quietly. An agent asked to "add tests" writes a happy path against whatever data happens to be in its
database, reports "all tests pass", and moves on. Months later nobody can say which rules are tested, the end-to-end
script fails on a fresh machine, and the test strategy document describes a setup that was deleted. This skill makes
the project's **rules** the input of test design, makes **coverage and evidence** checked outputs, and makes the test
spec a **living document** that is re-derived from the code whenever the code moves.

Follow the steps in order. Steps 1–5 run on every change. Step 6 runs on its own triggers.

## Step 1 — Load the test spec (or create it)

Look for, in this order:

1. `AGENTS.md` / `CLAUDE.md` → the section that names the test documents.
2. `docs/testing/test-spec.md` (or the project's equivalent: `TESTING.md`, `docs/testing-strategy.md`).
3. `docs/testing/coverage-matrix.md` and `testguard.toml` (the machine-checked rule coverage).
4. The rule source the spec names (a business-rules baseline, a PRD with rule IDs, an API contract).

**If they exist**: read the spec fully; it overrides this skill. Run `testguard drift` (or read the matrix) to see
where the project stands before you change anything.

**If they do not**: do not start writing tests. Generate them with
[references/spec-generator-prompt.md](references/spec-generator-prompt.md) using
[references/test-spec-template.md](references/test-spec-template.md), set up `testguard` (see
[references/testguard-setup.md](references/testguard-setup.md)), and present the spec, the rule list and the
baseline allowlist to the user for review. **An agent-written test spec is a proposal until a human approves it.**
If the project has no rule list, the generator derives one from the docs and code and marks every rule
`derived — confirm`; a human must confirm that list, because code can be wrong.

## Step 2 — Find the rules the change touches

Before writing code or tests, list:

- the rule IDs the change implements, changes or could break (search the rule source and the code that cites them);
- for each rule, the **layer** that implements it (domain/unit, persistence, API, process, UI) — test it there;
- the **case kinds** the rule needs, from the matrix in
  [references/case-design.md](references/case-design.md): happy, boundary, over, invalid, auth, concurrency,
  idempotency, time, failure. Not every rule needs every kind; write down which apply and why.

A change with no rule ID is either pure refactoring (existing tests must stay green and unchanged in meaning) or a
missing rule (stop and ask: a behaviour without a rule cannot be tested for correctness, only for "unchanged").

## Step 3 — Design the data, then the tests

Use [references/case-design.md](references/case-design.md). In short:

- **Every datum exists for a case.** Build each case's data in the test (builders/factories with valid defaults),
  not by relying on what a shared database happens to contain. Shared seeds hold only reference data (accounts,
  stations, catalogues), never the rows a test asserts on.
- **Boundaries are explicit values**: exactly at the limit, one over, one under, empty, one, many.
- **Time is fixed**: inject a clock; choose instants that matter (local midnight, DST change, cut-off ±1 s).
  Derive expected values from the same rules the code uses (time-zone database, currency tables), never from
  constants that depend on the machine's data.
- **Unique, tagged, cleaned up**: test data carries a unique prefix or run id, is marked as test data where the
  schema allows, and is removed by the test.
- **Realistic where realism is the rule**: addresses that geocode to land, names with accents, the real ranges.

Then write the tests, cheapest layer first: most rule cases belong in fast unit tests of the code that implements
the rule; end-to-end tests prove that the layers are wired together along each critical path, one or two
representative cases per path, not every boundary.

**Cite the rule in every test**: put the ID in the test name or a tag next to it, with the case kind —
`brP3_rejectsOneOverCapacity` / `// BR-P3:over`. That citation is what makes coverage measurable.

## Step 4 — Prove it

Run, at minimum:

- the full test suite in the same way CI runs it, from a clean state (fresh database or container, no local data);
- `testguard check` — every rule cited or allowlisted with a reason; no citation of a removed rule; required case
  kinds present; test reports show the expected number of tests ran and none failed; the spec references no
  path that no longer exists;
- `testguard matrix` — regenerate the matrix and commit it with the change.

Never report "tests pass" from memory or from a partial run. Report the command, the count and the result, and
point to CI where it exists. If a check fails, fix the test or the code; do not weaken the check, delete a test,
or add an allowlist entry without the user's explicit approval.

## Step 5 — Report

In the PR description or final reply:

- rule IDs touched, and for each the case kinds now covered (from the regenerated matrix);
- new or changed test data and why each datum exists;
- coverage delta (`testguard drift`: rules newly covered, coverage lost, new uncovered rules);
- anything you could not test, with the reason and an owner — never silently.

## Step 6 — Keep the spec alive (the loop)

The test spec, the matrix and the tests are re-derived from the code; they are never "done". Run
[references/evolution-loop.md](references/evolution-loop.md) on each trigger:

| Trigger | What the agent does |
|---|---|
| Every change (steps 2–5) | Update only the matrix rows and tests of the rules touched |
| A rule is added, changed or removed in the rule source | Same change adds/updates/removes its tests and matrix row; `testguard check` fails otherwise |
| A bug escapes (found after merge or in production) | Escape analysis: why did no test catch it? Add the missing case; if it is a *class* of miss, propose a new principle or failure pattern for the spec |
| Scheduled (nightly CI job or a scheduled agent) | `testguard drift --json`; open a maintenance PR for new uncovered rules, lost coverage, stale spec paths, flaky or skipped tests |
| A test becomes flaky or is skipped | Treat as a failure: fix the cause (time, ordering, shared data), never retry-until-green |

Spec changes are proposals: open them as a PR for human review, with the evidence (the drift report, the escaped bug)
that motivates them. Lowering a bar — deleting a test, widening an allowlist, removing a required case kind — always
needs the user's approval.

## Failure patterns to check

[references/failure-patterns.md](references/failure-patterns.md) lists 16 ways test suites fail in practice (tests
tied to one machine's data, constants baked from environment data, happy-path-only suites, unrun tests counted as
passed, stale strategy documents, …) with the check that prevents each. Read it when generating a spec and when
doing escape analysis; the generated spec must say how the project prevents every pattern that applies to it.
