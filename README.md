# agent-architecture-guard

Keep code written by coding agents (Claude Code, Codex, Cursor, …) and people inside a project's architecture, and
keep its tests traceable to its rules as both evolve. Two skills, each with a machine check ([中文](README.zh.md)):

- **architecture-guard** + `archguard`: where code goes, who owns which data.
- **test-guard** + `testguard`: which rules are tested with which cases, evidence that tests ran, and a loop that
  keeps the project's test spec, coverage matrix and tests evolving with the code.

Architecture layers, usable together or alone:

| Layer | What | Works with |
|---|---|---|
| 1. Protocol | `skill/architecture-guard/` — a four-step protocol (load the spec → place the change → code by the rules → prove it), a prompt that generates a project spec when there is none, and a spec template | Any agent: Claude Code loads it as a skill; others read it from `AGENTS.md` (`templates/agents-snippet.md`) |
| 2. Guards | `guards/archguard/archguard.py` — table ownership and a shrinking cross-domain write allowlist, from SQL and ORM mappings | Any language with SQL migrations (Java, Kotlin, TS/JS, Python, Go, C#) |
| 3. Layer rules | `kits/` — ArchUnit (Java), dependency-cruiser (TypeScript), import-linter (Python) templates | The project's own build |

CI, a pre-push hook and a PR template (`templates/`) make the checks unavoidable.

## Install into a project

```sh
./install.sh /path/to/project          # never overwrites; FORCE=1 updates the skill and archguard only
```

Then follow the printed steps: paste the AGENTS snippet, edit `architecture/archguard.toml`, run `archguard init`
(ownership file) and `archguard init --baseline` (allowlist today's violations, one reason each), add a layer-rule kit
and the CI job, and enable the hook.

## test-guard and testguard

`skill/test-guard/` makes the agent derive tests from rules: load (or generate, for human review) the project's test
spec → name the rules a change touches and the case kinds each needs → design data per case → prove it
(`testguard check`, regenerated matrix) → report; plus an evolution loop run on every rule change, every escaped
bug and on a schedule. `references/failure-patterns.md` lists 16 ways test suites fail in practice and the check
that prevents each; a generated spec must say how the project prevents every one that applies.

```sh
python3 tools/testguard/testguard.py check  --config testing/testguard.toml   # exit 1 on any error
python3 tools/testguard/testguard.py matrix --config testing/testguard.toml   # docs/testing/coverage-matrix.md
python3 tools/testguard/testguard.py drift  --config testing/testguard.toml --json   # for the scheduled loop
python3 tools/testguard/testguard.py init   --config testing/testguard.toml --baseline
```

`check` fails when a defined rule has no test citing it and is not allowlisted; an allowlist entry is covered or
removed (the list only shrinks); a test cites a rule that no longer exists; a rule family lacks its required case
kinds (`RULE-ID:boundary` tags); test reports (JUnit XML) are missing, show fewer tests than `min_tests`, or show
failures; the test spec names a path that no longer exists. Setup: `skill/test-guard/references/testguard-setup.md`.

## archguard

```sh
python3 tools/archguard/archguard.py check   --config architecture/archguard.toml   # exit 1 on any error
python3 tools/archguard/archguard.py measure --config architecture/archguard.toml [--json]
python3 tools/archguard/archguard.py init    --config architecture/archguard.toml [--baseline]
```

Python 3.11+, standard library only. `check` fails when:

- a table created by the migrations (after `DROP`/`RENAME`) has no owner, an owner entry names a table that does not exist, or an owner is not a known domain;
- data-access code (`data_access_pattern`) writes (`INSERT`/`UPDATE`/`DELETE`/`REPLACE`/`MERGE`, or maps an entity with JPA `@Table`, SQLAlchemy `__tablename__`, TypeORM `@Entity`) a table owned by another domain and the write is not in the allowlist;
- an allowlist entry no longer occurs (delete it — the list only shrinks) or lacks a reason or removal iteration (`permanent` allowed).

Allowlist line: `writer domain | File#function | table | reason | iteration that removes it`.

Limits: table names built at run time are not seen; domains come from file paths (`[[domains.rule]]`, first match wins, named group `domain`); comments are ignored; `ON DUPLICATE KEY UPDATE` is not a write.

Tests (both guards): `python3 -m unittest discover -s guards/tests`.

## Versioning

Projects pin copies of `archguard.py` and `testguard.py` (`tools/<guard>/`, each with a `VERSION` file) so a guard update never breaks a build unannounced. Update with `FORCE=1 ./install.sh`.
