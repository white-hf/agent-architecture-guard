#!/bin/sh
# Install the agent architecture guard into a project.
#   ./install.sh /path/to/project
# Copies: the skills (.claude/skills/architecture-guard, test-guard), the pinned guard scripts (tools/archguard, tools/testguard),
# starter config (architecture/), the pre-push hook (tools/git-hooks) and, if absent, a PR template.
# It never overwrites an existing file; re-run with FORCE=1 to update the skill and the script only.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dest=${1:?usage: install.sh /path/to/project}
[ -d "$dest" ] || { echo "no such directory: $dest"; exit 1; }
copy() { # src dst [force-allowed]
  if [ -e "$2" ] && { [ "${FORCE:-0}" != 1 ] || [ "${3:-}" != force ]; }; then echo "keep   $2"; return; fi
  mkdir -p "$(dirname "$2")"; cp -R "$1" "$2"; echo "write  $2"
}
mkdir -p "$dest/.claude/skills"
for skill in architecture-guard test-guard; do
  if [ -e "$dest/.claude/skills/$skill" ] && [ "${FORCE:-0}" = 1 ]; then rm -rf "$dest/.claude/skills/$skill"; fi
  copy "$here/skill/$skill" "$dest/.claude/skills/$skill" force
done
copy "$here/guards/archguard/archguard.py" "$dest/tools/archguard/archguard.py" force
copy "$here/guards/testguard/testguard.py" "$dest/tools/testguard/testguard.py" force
copy "$here/templates/testing/testguard.toml" "$dest/testing/testguard.toml"
copy "$here/templates/architecture/archguard.toml" "$dest/architecture/archguard.toml"
copy "$here/templates/hooks/pre-push" "$dest/tools/git-hooks/pre-push"
copy "$here/templates/github/pull_request_template.md" "$dest/.github/pull_request_template.md"
python3 "$here/guards/archguard/archguard.py" version > "$dest/tools/archguard/VERSION"
python3 "$here/guards/testguard/testguard.py" version > "$dest/tools/testguard/VERSION"
cat <<MSG

Next steps:
  1. Paste templates/agents-snippet.md into $dest/AGENTS.md (and CLAUDE.md if you use Claude Code).
  2. Edit architecture/archguard.toml (sources, domain rules, migrations).
  3. python3 tools/archguard/archguard.py init --config architecture/archguard.toml   # ownership file; set every owner
  4. python3 tools/archguard/archguard.py init --config architecture/archguard.toml --baseline   # allowlist today's violations; give each a reason
  5. Add the layer rules for your language from kits/ and the CI job from templates/ci/.
  6. Tests: follow .claude/skills/test-guard/SKILL.md step 1 (generate docs/testing/test-spec.md for review),
     edit testing/testguard.toml, then: python3 tools/testguard/testguard.py init --config testing/testguard.toml --baseline
  7. git config core.hooksPath tools/git-hooks
MSG
