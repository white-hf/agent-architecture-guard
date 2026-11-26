<!-- Paste into AGENTS.md / CLAUDE.md (read by Claude Code, Codex, Cursor and others). Adjust the paths. -->
## Coding Protocol (all agents)

Before writing or reviewing code, follow `.claude/skills/architecture-guard/SKILL.md` (plain Markdown; read it even if your tool has no skill support):

1. **Load the spec**: `docs/architecture.md` (modules, layers, where new code goes, definition of done). If it does not exist, generate it first with `.claude/skills/architecture-guard/references/spec-generator-prompt.md` and get it reviewed.
2. **Place the change first**: name the owning domain, module and layer of every new class or file; never write another domain's tables.
3. **Code by the rules**, copying the reference implementations named in the spec, not the nearest file.
4. **Prove it**: the full build with its architecture tests, `archguard check --config architecture/archguard.toml`, and the end-to-end tests listed in the spec. Report placement, escape hatches and cross-domain writes in the PR.

Architecture checks are hard rules. If one fails, move the code; do not weaken a rule, skip it or add an allowlist entry without the maintainer's approval. Register every new table in `architecture/table-ownership.properties` in the same change as its migration.
