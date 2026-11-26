# Failure patterns of test suites

Each pattern was observed in a real project built largely by coding agents. A generated test spec must state, for
every pattern that applies, **how this project prevents it** (a check, a rule in the spec, or an accepted risk with
an owner). Escape analysis (evolution loop) adds new patterns here or to the project spec.

| # | Pattern | How it showed up | Prevention |
|---|---|---|---|
| F1 | **Tests depend on one machine's data** | The end-to-end suite used driver id 101 and an admin role that existed only in a long-lived dev database; on a fresh database it failed at once | Tests create the data they assert on; shared seeds hold reference data only; CI runs on a fresh database/container; look entities up by natural key, never by hard-coded surrogate id |
| F2 | **Expected values baked from environment data** | Two tests hard-coded Vancouver's UTC−8 offset for a future date; a newer time-zone database keeps the province on UTC−7 and the tests broke on the CI JDK | Fixed clocks; compute expected values with the same library rules the code uses; prefer zones/tables whose rules are stable when only formatting is under test |
| F3 | **Verification is the agent's own report** | "All tests pass" lived only in PR descriptions; nobody could tell whether the suite had run | CI on a neutral machine for every PR; reports read from test output (JUnit XML), not from prose; `testguard check` evidence section |
| F4 | **Rules without tests, invisibly** | 46 business rules, 21 cited by any test; nobody knew which 25 were missing | Every test cites rule IDs; `testguard` coverage with a shrinking allowlist; the matrix is generated, not claimed |
| F5 | **Happy path only** | The flagship E2E delivered 8 of 10 parcels and failed 2; capacity limits, freeze-after-publish, partial arrival, unroutable addresses, business-day boundaries and duplicate submits had no data at all | Case kinds per rule (case-design.md); `require_kinds` for critical rule families |
| F6 | **Tests that are not run rot** | An API changed its response shape; the E2E script that called it was only run by hand and stayed broken for several iterations | Every test runs automatically somewhere (per PR, after merge, nightly); a suite nobody runs is deleted or scheduled |
| F7 | **"Passes" because nothing ran** | A filtered test command can match zero tests and still exit 0; an architecture test can import zero classes and find no violation | `min_tests` in testguard evidence; guard tests assert they saw a plausible number of classes/files |
| F8 | **Process starts but is empty** | After a refactor the service started with zero repositories and every endpoint returned 404; unit tests were green | A full-context smoke test per deployable process asserting key routes and components exist |
| F9 | **Two definitions drift apart** | A state was added to the domain enum but not to the database CHECK constraint; failed only at run time | Consistency tests between paired definitions (enum ↔ constraint, entity ↔ schema with validation at startup, API contract ↔ DTO) |
| F10 | **Scripts tied to one OS** | E2E scripts wrote to macOS-only paths and used BSD-only `mktemp`; failed on Linux CI | Run scripts in CI on the target OS; POSIX-portable commands; paths from `${TMPDIR:-/tmp}` |
| F11 | **Stale test strategy document** | The strategy still described an in-memory profile that had been deleted | The spec references real paths/commands; `testguard` fails on paths that no longer exist; the loop re-derives the spec |
| F12 | **Demo, test and production data mixed** | Migrations inserted demo stations and parcels, so every environment — production included — received them | Migrations carry schema and required reference data only; demo/test data in separate seed scripts; test rows flagged |
| F13 | **Shared mutable state between tests** | Tests sharing one database order-depend on each other and fail when run alone or in parallel | One database/context per test class or transaction rollback; unique keys per run; no reliance on execution order |
| F14 | **Retry-until-green** | Flaky tests are re-run instead of fixed, hiding real races | Flakiness is a failure: find the cause (clock, ordering, shared data, async wait) |
| F15 | **Mocks that prove nothing** | A test mocks the repository it is meant to test, or asserts the mock was called instead of the outcome | Mock only across process/network boundaries; assert observable outcomes (state, response, emitted event) |
| F16 | **The test database is not the production database** | Persistence tests ran on H2 in MySQL mode; set-based `UPDATE … JOIN` and the conditional updates that guard concurrency behave differently and were only exercised end-to-end | Run persistence and concurrency tests on the production engine (a container in CI); keep in-memory databases for speed only where the SQL is portable |

## Escape analysis template

When a bug reaches main or production, answer before fixing:

1. Which rule does the bug violate? If none, the rule source is missing a rule — propose it.
2. Which case kind would have caught it? Was that kind listed for the rule?
3. At which layer should the test live? Why did existing tests at that layer not catch it (no case, wrong data,
   mocked away, not run)?
4. Is this a one-off or a class (a new failure pattern)? If a class, propose the prevention for the spec.

Record the answers in the PR that fixes the bug; the new test cites the rule and the case kind.
