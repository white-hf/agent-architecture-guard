# Prompt: generate a project architecture spec

Use this when a repository has no architecture spec. Paste it to the agent (or follow it yourself). The output is a
**proposal**: a human reviews and approves it before anyone codes against it.

---

You are preparing the architecture spec that every coding agent in this repository must follow. Do not change any
production code in this task. Work in three passes and show your evidence.

## Pass 1 — Discover (facts only, with file paths and counts)

1. **Deployable units**: which processes/apps are built and run (main classes, Dockerfiles, compose, package.json
   apps), their ports and who calls them.
2. **Build modules** and their declared dependencies (Maven/Gradle modules, workspaces, packages). Draw the graph.
3. **Business domains**: read the product docs, API routes, database tables and package names. List candidate
   domains with their tables and endpoints. Note where one domain is spread across several modules or packages.
4. **Layers in practice**: for 3–5 representative features, trace request → controller → service → data access.
   Record where business rules, transactions and SQL actually sit.
5. **Persistence**: ORM vs raw SQL, migrations tool and location, who runs migrations, entities per table.
6. **Existing guardrails**: architecture tests, lint rules, CI jobs, PR templates, hooks.
7. **Measurements** (run them, don't estimate): SQL/DB calls outside the data-access layer; classes over 400 lines;
   writes to tables owned by another domain; dependency cycles between packages.

## Pass 2 — Decide the target (propose, with reasons)

1. Domain list and the module each lives in (shared module only when more than one deployable uses it).
2. Layer names, responsibilities and the dependency direction; where transactions start.
3. Table ownership: table → owning domain.
4. Persistence rules: ORM scope, allowed raw-SQL categories, migration ownership and compatibility rule.
5. Cross-domain rule: how one domain uses another (application service call in the same transaction; events for
   other processes).
6. Naming: package roots, layer package names, forbidden names.
7. Reference implementation: the one context new code should copy.
8. Exceptions that exist today, each with a reason and a plan (an allowlist that may only shrink).

## Pass 3 — Write the spec and its enforcement

Write `docs/architecture-spec.md` (or the project's docs location) following
[spec-template.md](spec-template.md). Every MUST rule needs an enforcement line: the test, lint rule or CI step that
fails when it is broken, or "manual review" if no automatic check is possible yet (and a proposal to add one).

Then list the checks to add (architecture tests, guard tests, CI job), smallest first, and the measurements from
pass 1 as the baseline future work must not exceed.

Finish with the open questions that need a human decision. Do not resolve product questions yourself.
