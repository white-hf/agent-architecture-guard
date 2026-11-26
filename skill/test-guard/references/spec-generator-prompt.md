# Prompt: generate the project's test spec

Use this prompt (with any agent) when a project has no test spec, or to regenerate one section by section.

---

You are generating the test spec for this repository. Produce `docs/testing/test-spec.md` following
`test-spec-template.md`, plus `testguard.toml`, a baseline allowlist and a coverage matrix. Work from evidence in the
repository only; every claim must point to a file, a command you ran, or a test report.

1. **Find the rule source.** Look for a business-rules baseline, PRD tables with rule IDs, API contracts with error
   codes, ADRs. If rules have IDs, record the ID regex and where they are defined. If there are no IDs, derive a rule
   list from the docs, then from the code (validations, state machines, limits, permission checks), give each a
   stable ID, mark each `derived — confirm`, and put the list in a reviewable file. Do not invent rules the code and
   docs do not support.
2. **Inventory the tests.** For each test directory: framework, layer, how data is created, whether it needs a
   database or network, how it is run, whether CI runs it. Run the suites; record counts and failures. Note tests
   that are never run automatically.
3. **Map rules to tests.** Find existing citations (rule IDs in names, comments, tags). Configure `testguard`
   citation patterns to match the project's conventions. Run `testguard check` and `testguard matrix`.
   Then go through every uncovered rule by hand and sort it into one of three groups: **tested but not cited**
   (name the existing tests: the fix is adding the ID, not new tests), **partly tested** (name what is missing), or
   **no test**. In the pilot project 14 of 25 "uncovered" rules were tested but not cited; skipping this step
   overstates the gap and sends effort to the wrong place. Record the group in each allowlist reason.
4. **Check the failure patterns** in `failure-patterns.md` one by one against this repository and record, for each,
   whether it applies and how the project prevents it today (or that it does not — that is a finding).
5. **Choose required case kinds** per rule family using `case-design.md` (limits → boundary/over; permissions → auth;
   state machines → invalid; external input → idempotency; dates → time).
6. **Baseline.** `testguard init --baseline` allowlists today's uncovered rules; give each a reason and the iteration
   that will cover it. Prioritise by risk: money, custody/ownership, permissions, data loss, legal.
7. **Present for review**: the spec (status PROPOSED), the rule list if derived, the matrix, the allowlist and a
   short list of the most important gaps. Do not write new tests before the spec is reviewed, except to fix tests
   that are broken today.

Output nothing that is not grounded in the repository. Where you are unsure, say so in the spec as an open question.
