#!/usr/bin/env python3
"""archguard: language-agnostic architecture guards for codebases written by people and coding agents.

Checks (standard library only, Python 3.11+):
  table-ownership   every table created by a migration has exactly one owning domain
  cross-domain      data-access code writes only tables owned by its own domain, except allowlisted entries;
                    the allowlist may only shrink (stale entries fail)
Commands:
  archguard check   [--config archguard.toml]        run the checks, exit 1 on any error
  archguard measure [--config archguard.toml] [--json] print the baseline metrics
  archguard init    [--config archguard.toml] [--baseline]  scaffold the ownership file / allowlist from the code

See README.md for the configuration format.
"""
from __future__ import annotations

import argparse
import bisect
import fnmatch
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "0.1.0"

WRITE_RE = re.compile(
    r"(?<![A-Za-z_])(?P<kind>INSERT\s+(?:IGNORE\s+)?INTO|REPLACE\s+INTO|MERGE\s+INTO|UPDATE|DELETE\s+FROM)"
    r"\s+[`\"\[]?(?P<table>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
ENTITY_TABLE_RES = [
    re.compile(r"@Table\s*\(\s*(?:name\s*=\s*)?\"(?P<table>[A-Za-z_][A-Za-z0-9_]*)\""),          # JPA / Jakarta
    re.compile(r"__tablename__\s*=\s*[\"'](?P<table>[A-Za-z_][A-Za-z0-9_]*)[\"']"),             # SQLAlchemy
    re.compile(r"@Entity\s*\(\s*(?:\{\s*name\s*:\s*)?[\"'](?P<table>[A-Za-z_][A-Za-z0-9_]*)[\"']"),  # TypeORM
]
CREATE_RE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(?P<table>[A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
DROP_RE = re.compile(r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?[`\"\[]?(?P<table>[A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
RENAME_RE = re.compile(r"\bRENAME\s+TABLE\s+[`\"]?(?P<old>\w+)[`\"]?\s+TO\s+[`\"]?(?P<new>\w+)", re.IGNORECASE)
# SQL-shaped string literals (uppercase keywords plus their clause), used only by `measure`.
SQL_LITERAL_RE = re.compile(r"[\"'`](?:\s|\\n)*(?:SELECT\s[^\"'`;]*?\bFROM\b|INSERT\s+(?:IGNORE\s+)?INTO\b|UPDATE\s+\w+\s+SET\b|DELETE\s+FROM\b|MERGE\s+INTO\b)")

# Line-anchored function-declaration patterns (one pass per file, no nested quantifiers).
_JVM_DECL = r"^\s*(?:@[\w.]+(?:\([^)\n]*\))?\s+)*(?:(?:public|protected|private|static|final|synchronized|abstract|default|internal|async|override|virtual|open|suspend)\s+)*(?:<[^>\n]+>\s+)?[\w.\[\]?]+(?:<[^\n(=;]*>)?\s+(?P<name>\w+)\s*\("
FUNCTION_RES = {
    ".java": re.compile(_JVM_DECL, re.M),
    ".cs": re.compile(_JVM_DECL, re.M),
    ".kt": re.compile(r"^\s*(?:[\w]+\s+)*fun\s+(?:<[^>\n]+>\s*)?(?:[\w.]+\.)?(?P<name>\w+)\s*\(", re.M),
    ".py": re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>\w+)\s*\(", re.M),
    ".ts": re.compile(r"^\s*(?:export\s+)?(?:(?:public|private|protected|static|async|readonly)\s+)*(?:function\s+)?(?P<name>\w+)\s*(?:<[^>\n]+>)?\s*\([^)\n]*\)?[^;\n]*\{?\s*$", re.M),
    ".js": re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+)?(?P<name>\w+)\s*\([^)\n]*\)?[^;\n]*\{?\s*$", re.M),
    ".go": re.compile(r"^func\s+(?:\([^)\n]*\)\s*)?(?P<name>\w+)\s*\(", re.M),
}
KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new", "else", "try", "synchronized"}


# ---------------------------------------------------------------------------------------------------- config
@dataclass
class DomainRule:
    pattern: re.Pattern
    domain: str | None


@dataclass
class Config:
    root: Path
    sources: list[str]
    excludes: list[str]
    data_access: re.Pattern
    domain_rules: list[DomainRule]
    aliases: dict[str, str]
    known_domains: set[str]
    migrations: list[str]
    ownership_file: Path
    allowlist_file: Path
    large_file_lines: int = 400
    extra: dict = field(default_factory=dict)


def load_config(path: Path) -> Config:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    root = (path.parent / data.get("root", ".")).resolve()
    src = data.get("sources", {})
    dom = data.get("domains", {})
    schema = data.get("schema", {})
    writes = data.get("writes", {})
    rules = [DomainRule(re.compile(r["pattern"]), r.get("domain")) for r in dom.get("rule", [])]
    if not rules:
        raise SystemExit("archguard: [[domains.rule]] is required")
    return Config(
        root=root,
        sources=src.get("include", ["**/*"]),
        excludes=src.get("exclude", []) + ["**/node_modules/**", "**/target/**", "**/build/**", "**/dist/**", "**/.git/**"],
        data_access=re.compile(src.get("data_access_pattern", r"/(persistence|repository|repositories|dao|db)/")),
        domain_rules=rules,
        aliases=dom.get("aliases", {}),
        known_domains=set(dom.get("known", [])),
        migrations=schema.get("migrations", []),
        ownership_file=root / schema.get("ownership", "architecture/table-ownership.properties"),
        allowlist_file=root / writes.get("allowlist", "architecture/cross-domain-writes.allowlist"),
        large_file_lines=data.get("measure", {}).get("large_file_lines", 400),
        extra=data,
    )


# ---------------------------------------------------------------------------------------------------- helpers
def rel(cfg: Config, p: Path) -> str:
    return p.relative_to(cfg.root).as_posix()


def matches(relpath: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(relpath, g) for g in globs)


def source_files(cfg: Config) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(cfg.root):
        dirnames[:] = [d for d in dirnames if d not in {"node_modules", ".git", "target", "build", "dist", ".venv"}]
        for f in filenames:
            p = Path(dirpath) / f
            r = rel(cfg, p)
            if matches(r, cfg.sources) and not matches(r, cfg.excludes):
                out.append(p)
    return sorted(out)


def domain_of(cfg: Config, relpath: str) -> str | None:
    for rule in cfg.domain_rules:
        m = rule.pattern.search(relpath)
        if m:
            d = rule.domain or m.groupdict().get("domain")
            return cfg.aliases.get(d, d) if d else None
    return None


def function_index(text: str, suffix: str) -> list[tuple[int, str]]:
    """Start offsets and names of function declarations, found in one pass."""
    regex = FUNCTION_RES.get(suffix)
    if regex is None:
        return []
    out = []
    for m in regex.finditer(text):
        name = m.group("name")
        if name and name not in KEYWORDS:
            out.append((m.start(), name))
    return out


def enclosing_function(index: list[tuple[int, str]], pos: int) -> str:
    i = bisect.bisect_right([p for p, _ in index], pos) - 1
    return index[i][1] if i >= 0 else "?"


def strip_comments(text: str, suffix: str) -> str:
    """Blank out comments (keeping offsets) so commented-out SQL is not reported."""
    if suffix in {".py"}:
        return re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), text)
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    return re.sub(r"(?<![:\"'])//[^\n]*", lambda m: " " * len(m.group(0)), text)


def read_properties(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------------------------------------------- schema
def tables_from_migrations(cfg: Config) -> dict[str, str]:
    """Tables existing after all migrations ran, mapped to the migration that created them."""
    files = []
    for g in cfg.migrations:
        files += sorted(cfg.root.glob(g), key=lambda p: natural_key(p.name))
    tables: dict[str, str] = {}
    for f in files:
        text = strip_comments(f.read_text(encoding="utf-8", errors="replace"), ".sql")
        events = [(m.start(), "create", m.group("table").lower(), None) for m in CREATE_RE.finditer(text)]
        events += [(m.start(), "drop", m.group("table").lower(), None) for m in DROP_RE.finditer(text)]
        events += [(m.start(), "rename", m.group("old").lower(), m.group("new").lower()) for m in RENAME_RE.finditer(text)]
        for _, kind, table, new in sorted(events):
            if kind == "create":
                tables[table] = f.name
            elif kind == "drop":
                tables.pop(table, None)
            elif kind == "rename" and table in tables:
                tables[new] = tables.pop(table)
    return tables


def natural_key(name: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


# ---------------------------------------------------------------------------------------------------- scanning
@dataclass(frozen=True)
class Write:
    writer: str
    location: str  # File#function or File#@Table
    table: str
    path: str

    def key(self) -> tuple[str, str, str]:
        return (self.writer, self.location, self.table)


def scan_writes(cfg: Config, owners: dict[str, str]) -> tuple[list[Write], int]:
    """All writes in data-access code whose target table is owned by another domain, and the total write count."""
    found: list[Write] = []
    total = 0
    for p in source_files(cfg):
        r = rel(cfg, p)
        if not cfg.data_access.search("/" + r):
            continue
        writer = domain_of(cfg, r)
        if writer is None:
            continue
        raw = p.read_text(encoding="utf-8", errors="replace")
        text = strip_comments(raw, p.suffix)
        stem = p.stem
        index = function_index(text, p.suffix)
        for m in WRITE_RE.finditer(text):
            table = m.group("table").lower()
            prefix = text[max(0, m.start() - 12):m.start()].upper()
            if m.group("kind").upper() == "UPDATE" and re.search(r"KEY\s*$", prefix):
                continue  # ON DUPLICATE KEY UPDATE <column>
            if table not in owners:
                continue
            total += 1
            if owners[table] != writer:
                found.append(Write(writer, f"{stem}#{enclosing_function(index, m.start())}", table, r))
        for regex in ENTITY_TABLE_RES:
            for m in regex.finditer(text):
                table = m.group("table").lower()
                if table in owners:
                    total += 1
                    if owners[table] != writer:
                        found.append(Write(writer, f"{stem}#@entity", table, r))
    return found, total


@dataclass
class AllowEntry:
    writer: str
    location: str
    table: str
    reason: str
    remove_by: str
    line: int

    def key(self) -> tuple[str, str, str]:
        return (self.writer, self.location, self.table)


def read_allowlist(path: Path) -> list[AllowEntry]:
    entries = []
    if not path.exists():
        return entries
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = [x.strip() for x in s.split("|")]
        parts += [""] * (5 - len(parts))
        entries.append(AllowEntry(*parts[:5], line=i))
    return entries


# ---------------------------------------------------------------------------------------------------- checks
def check(cfg: Config) -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []
    owners = read_properties(cfg.ownership_file)
    owners = {k.lower(): cfg.aliases.get(v, v) for k, v in owners.items()}

    # table-ownership
    if cfg.migrations:
        tables = tables_from_migrations(cfg)
        for t, mig in sorted(tables.items()):
            if t not in owners:
                errors.append(f"table-ownership: table '{t}' (created in {mig}) has no owner in {rel(cfg, cfg.ownership_file)}")
        for t in sorted(set(owners) - set(tables)):
            errors.append(f"table-ownership: '{t}' is in {rel(cfg, cfg.ownership_file)} but no migration creates it")
    if cfg.known_domains:
        for t, d in sorted(owners.items()):
            if d not in cfg.known_domains:
                errors.append(f"table-ownership: table '{t}' is owned by unknown domain '{d}'")

    # cross-domain writes with a shrinking allowlist
    writes, _ = scan_writes(cfg, owners)
    allow = read_allowlist(cfg.allowlist_file)
    allowed = {e.key(): e for e in allow}
    seen = set()
    for w in writes:
        if w.key() in allowed:
            seen.add(w.key())
        else:
            errors.append(f"cross-domain: {w.writer} writes '{w.table}' (owned by {owners[w.table]}) in {w.path} "
                          f"[{w.location}] — call the owner's application service instead, or get an allowlist entry approved")
    for e in allow:
        if e.key() not in seen:
            errors.append(f"cross-domain: allowlist line {e.line} ({e.writer} | {e.location} | {e.table}) no longer occurs; delete it")
        if not e.reason or not e.remove_by:
            errors.append(f"cross-domain: allowlist line {e.line} needs a reason and a removal iteration (or 'permanent')")
        elif "TODO" in e.reason or e.remove_by.upper() == "TBD":
            warnings.append(f"cross-domain: allowlist line {e.line} still has a placeholder reason or removal iteration")
    for w in warnings:
        print("warning:", w, file=sys.stderr)
    return errors


def measure(cfg: Config) -> dict:
    owners = {k.lower(): cfg.aliases.get(v, v) for k, v in read_properties(cfg.ownership_file).items()}
    writes, total = scan_writes(cfg, owners)
    sql_outside, large, files = 0, [], 0
    for p in source_files(cfg):
        r = rel(cfg, p)
        files += 1
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.count("\n") + 1
        if lines > cfg.large_file_lines:
            large.append((r, lines))
        if not cfg.data_access.search("/" + r):
            sql_outside += len(SQL_LITERAL_RE.findall(strip_comments(text, p.suffix)))
    allow = read_allowlist(cfg.allowlist_file)
    return {
        "version": VERSION,
        "source_files": files,
        "tables": len(tables_from_migrations(cfg)) if cfg.migrations else None,
        "write_statements_to_known_tables": total,
        "cross_domain_writes": len(writes),
        "allowlist_entries": len(allow),
        "allowlist_permanent": sum(1 for e in allow if e.remove_by.lower() == "permanent"),
        "sql_literals_outside_data_access": sql_outside,
        f"files_over_{cfg.large_file_lines}_lines": len(large),
        "largest_files": sorted(large, key=lambda x: -x[1])[:10],
    }


def init(cfg: Config, baseline: bool) -> None:
    cfg.ownership_file.parent.mkdir(parents=True, exist_ok=True)
    if not cfg.ownership_file.exists():
        tables = tables_from_migrations(cfg) if cfg.migrations else {}
        body = "# table=owning domain (one owner per table; only the owner writes it)\n"
        body += "".join(f"{t}=TODO\n" for t in sorted(tables))
        cfg.ownership_file.write_text(body, encoding="utf-8")
        print(f"wrote {rel(cfg, cfg.ownership_file)} with {len(tables)} tables; set every owner")
    if baseline:
        owners = {k.lower(): cfg.aliases.get(v, v) for k, v in read_properties(cfg.ownership_file).items()}
        if any(v == "TODO" for v in owners.values()):
            raise SystemExit("archguard: set every owner in the ownership file before --baseline")
        writes, _ = scan_writes(cfg, owners)
        existing = {e.key() for e in read_allowlist(cfg.allowlist_file)}
        new = sorted({w.key() for w in writes} - existing)
        with cfg.allowlist_file.open("a", encoding="utf-8") as f:
            if not existing:
                f.write("# writer domain | File#function | table | reason | iteration that removes it (or 'permanent')\n")
            for k in new:
                f.write(f"{k[0]} | {k[1]} | {k[2]} | TODO reason | TBD\n")
        print(f"appended {len(new)} baseline entries to {rel(cfg, cfg.allowlist_file)}; fill in every reason")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="archguard", description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["check", "measure", "init", "version"])
    ap.add_argument("--config", default="archguard.toml")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    args = ap.parse_args(argv)
    if args.command == "version":
        print(VERSION)
        return 0
    cfg = load_config(Path(args.config).resolve())
    if args.command == "check":
        errors = check(cfg)
        for e in errors:
            print("error:", e)
        print(f"archguard {VERSION}: {'FAILED' if errors else 'OK'} ({len(errors)} error(s))")
        return 1 if errors else 0
    if args.command == "measure":
        m = measure(cfg)
        print(json.dumps(m, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in m.items()))
        return 0
    init(cfg, args.baseline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
