---
name: architecture-guard
description: Load before writing or changing backend code, before planning an iteration, and before reviewing a PR. Finds the project's architecture spec (or generates one when the project has none), decides where new code belongs (domain, module, layer), applies the rules while coding, and runs the project's architecture checks before declaring done. Tool-agnostic: the same files work for Claude Code, Codex and other agents.
---

# Architecture guard

Code drifts into a mess when an agent's only goal is "the feature works and the tests pass": the easiest place to
put new code is the biggest nearby class, and every shortcut is copied by the next agent. This skill makes the
architecture an explicit input to every change and a checked output of it.

Follow the four steps in order. Do not skip step 1 because the change looks small.

## Step 1 — Load the spec (or create it)

Look for the project's architecture spec, in this order:

1. `AGENTS.md` / `CLAUDE.md` → the section that names the architecture documents.
2. A principles / architecture document (e.g. `docs/design/code-architecture-principles.md`, `ARCHITECTURE.md`,
   `docs/adr/`), the persistence ADR and the business-rules baseline it links to.
3. Executable rules: ArchUnit / jMolecules (Java), dependency-cruiser or eslint-plugin-boundaries (TypeScript),
   import-linter (Python), `deny`-style module rules, plus any guard tests.

**If the project has a spec**: read it fully. It overrides anything in this skill.

**If it has none**: do not start coding. Generate one with
[references/spec-generator-prompt.md](references/spec-generator-prompt.md) using the structure in
[references/spec-template.md](references/spec-template.md), present it to the user for review, and only then
continue. A spec written by an agent is a proposal until a human approves it.

## Step 2 — Place the change before writing it

Answer these in writing (in the plan, the PR description or your reply) before touching code:

| Question | Typical answer shape |
|---|---|
| Which business domain owns this behaviour? | One domain. If two seem to own it, the rule belongs to the one whose data/invariant it protects. |
| Which deployable/module does that domain live in? | Shared module if more than one process uses the domain; otherwise the single process that uses it. |
| Which layer? | Rule → `domain`; use case / transaction → `application`; SQL / ORM → `persistence`; HTTP → `web`; external system → `gateway` |
| Which business rule ID does it implement or change? | Cite the ID. A changed rule needs the rules baseline updated and reviewed first. |
| Does it touch another domain's data? | Never write another domain's tables. Call that domain's application service in the same transaction. |
| Does it need SQL outside the ORM? | Only the escape-hatch categories the persistence ADR allows, in `persistence`, with a category comment. |

If an answer is unclear, ask the user rather than guess. Placing code wrongly is cheap to avoid and expensive to undo.

## Step 3 — Write it by the rules

Universal rules (the project spec may add to or tighten them):

1. **Dependencies point inward**: web → application → domain; persistence and gateways implement what application
   needs. Domain code depends only on the language runtime and the shared kernel.
2. **One domain, one place**: a domain's model, use cases and data access live in one module/package tree. API or UI
   modules are adapters only.
3. **Business rules only in the domain layer**, each with a database-free unit test named after its rule ID.
   One state machine per aggregate; illegal transitions raise a stable error code.
4. **Data ownership**: each table has one owning domain. Only the owner writes it. Others call the owner's
   application service; read models may join for reporting only where the spec allows.
5. **Transactions** begin in the application layer; one command is all-or-nothing; cross-domain calls join the
   caller's transaction. Integration events go through the transactional outbox.
6. **Persistence**: ORM for entity lifecycle; set-based or dialect SQL only as documented escape hatches; one
   entity per table; schema changes only via versioned migrations, expand-then-contract when processes deploy
   independently.
7. **Time and identity**: no zone-less clock reads; store UTC; derive business days explicitly. Never trust a
   caller-supplied actor id when the token carries one.
8. **No dead structure**: no "service" or "domain service" without a production caller; documents say whether they
   describe the current state or a proposal.
9. **Copy the reference implementation, not the nearest file**: the spec names the reference contexts; legacy code
   is not a template.

## Step 4 — Prove it before declaring done

Run, at minimum:

- the full build with tests (e.g. `mvn clean verify`), which includes the architecture tests;
- the data-ownership guard if the project has one (`archguard check`): new tables
  registered with an owner, no new cross-domain write, allowlists only shrink;
- the project's end-to-end or contract tests listed in the spec;
- for a structural change, a start-up smoke test of every process.

Then report, in the PR description or final reply:

- domain / module / layer of every new class;
- rule IDs implemented and their tests;
- any new escape-hatch SQL (class + category) and any new cross-domain write (must be zero, or an
  allowlist entry with a reason that a human approved);
- checks run and their results, including failures.

If an architecture test fails, fix the placement. Do not weaken, skip or baseline the rule without the user's approval.

## Reviewing someone else's change

Apply step 2 to every new class and step 4's report to the PR. Flag: logic in controllers or API modules, SQL
outside persistence, writes to another domain's tables, rules without rule-ID tests, new modules or packages that
the spec does not define, and documents that present plans as facts.
