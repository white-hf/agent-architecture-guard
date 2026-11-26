# agent-architecture-guard

Keep code written by coding agents (Claude Code, Codex, Cursor, …) and people inside a project's architecture.
Three layers, usable together or alone ([中文](README.zh.md)):

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

Tests: `python3 -m unittest discover -s guards/tests`.

## Versioning

Projects pin a copy of `archguard.py` (`tools/archguard/`, plus a `VERSION` file) so a guard update never breaks a build unannounced. Update with `FORCE=1 ./install.sh`.
