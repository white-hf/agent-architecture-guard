#!/usr/bin/env python3
"""testguard: keeps a project's tests traceable to its rules, and its test spec in step with the code.

Language-agnostic, standard library only (Python 3.11+). It reads:
  * the rule definitions (e.g. a business-rules table in the docs) and their IDs,
  * the tests (any language) and the rule IDs they cite, optionally with a case kind (`BR-P3:boundary`),
  * optionally the test reports (JUnit XML, emitted by most test runners) as evidence that tests ran,
  * optionally the test-spec documents, whose referenced paths must still exist.

Commands:
  testguard check   [--config testguard.toml]   fail on: an uncovered rule not in the allowlist, a stale allowlist
                                                entry, a test citing an unknown rule, missing required case kinds,
                                                no/failed test reports, a spec referencing a path that is gone
  testguard matrix  [--config ...] [--out FILE] write the coverage matrix (rule -> case kinds -> tests) as Markdown
  testguard drift   [--config ...] [--json]     report what changed since the matrix was written (for a loop/schedule)
  testguard init    [--config ...] [--baseline] allowlist today's uncovered rules (each needs a reason before review)
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "0.1.0"
SKIP_DIRS = {"node_modules", ".git", "target", "build", "dist", ".venv", "__pycache__"}
DEFAULT_KINDS = ["happy", "boundary", "over", "invalid", "auth", "concurrency", "idempotency", "time", "failure"]
MATRIX_MARKER = "<!-- testguard:matrix"


# ---------------------------------------------------------------------------------------------------- config
@dataclass
class Citation:
    regex: re.Pattern
    template: str | None  # e.g. "BR-{1}{2}" builds the ID from groups; None = the whole match is the ID


@dataclass
class Config:
    root: Path
    rule_files: list[str]
    rule_definition: re.Pattern
    test_include: list[str]
    test_exclude: list[str]
    citations: list[Citation]
    kinds: list[str]
    require_kinds: dict[str, list[str]]
    allowlist_file: Path
    junit_globs: list[str]
    min_tests: int
    spec_files: list[str]
    matrix_file: Path
    path_prefixes: list[str] = field(default_factory=list)


def load_config(path: Path) -> Config:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    root = (path.parent / data.get("root", ".")).resolve()
    rules, tests, ev, docs = data.get("rules", {}), data.get("tests", {}), data.get("evidence", {}), data.get("docs", {})
    if not rules.get("id_pattern"):
        raise SystemExit("testguard: [rules] id_pattern is required (e.g. 'BR-[A-Z]+\\d+[a-z]?'); a generic default would match 'UTF-8'")
    id_regex = rules["id_pattern"]
    definition = rules.get("definition_pattern", r"^\|\s*(?P<id>" + id_regex + r")\s*\|\s*(?P<title>[^|\n]+)")
    cites = [Citation(re.compile(r"(?<![\w-])" + id_regex + r"(?![\w])"), None)]
    for c in tests.get("citation", []):
        cites.append(Citation(re.compile(c["pattern"]), c.get("template")))
    if not rules.get("files"):
        raise SystemExit("testguard: [rules] files is required")
    return Config(
        root=root,
        rule_files=rules["files"],
        rule_definition=re.compile(definition, re.M),
        test_include=tests.get("include", ["**/test/**", "**/tests/**", "**/*.test.*", "**/*_test.*", "**/test_*.py"]),
        test_exclude=tests.get("exclude", []),
        citations=cites,
        kinds=tests.get("kinds", DEFAULT_KINDS),
        require_kinds=tests.get("require_kinds", {}),
        allowlist_file=root / rules.get("allowlist", "testing/uncovered-rules.allowlist"),
        junit_globs=ev.get("junit", []),
        min_tests=ev.get("min_tests", 1),
        spec_files=docs.get("spec", []),
        matrix_file=root / docs.get("matrix", "docs/testing/coverage-matrix.md"),
        path_prefixes=docs.get("path_prefixes", []),
    )


# ---------------------------------------------------------------------------------------------------- scanning
def walk(cfg: Config, include: list[str], exclude: list[str]) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(cfg.root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            p = Path(dirpath) / f
            r = p.relative_to(cfg.root).as_posix()
            if any(fnmatch.fnmatch(r, g) for g in include) and not any(fnmatch.fnmatch(r, g) for g in exclude):
                out.append(p)
    return sorted(out)


def rules(cfg: Config) -> dict[str, str]:
    """Rule ID -> title, in definition order; the first definition wins."""
    out: dict[str, str] = {}
    for g in cfg.rule_files:
        for p in sorted(cfg.root.glob(g)):
            for m in cfg.rule_definition.finditer(p.read_text(encoding="utf-8", errors="replace")):
                out.setdefault(m.group("id"), " ".join(m.group("title").split())[:120])
    return out


@dataclass
class Cite:
    rule: str
    kind: str | None
    file: str
    line: int


def citations(cfg: Config) -> list[Cite]:
    found: list[Cite] = []
    kind_re = re.compile(r"\s*[:/]\s*(" + "|".join(map(re.escape, cfg.kinds)) + r")\b") if cfg.kinds else None
    for p in walk(cfg, cfg.test_include, cfg.test_exclude):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(cfg.root).as_posix()
        line_starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
        for c in cfg.citations:
            for m in c.regex.finditer(text):
                rule = c.template.format(*([m.group(0)] + list(m.groups()))) if c.template else m.group(0)
                kind = None
                if kind_re:
                    k = kind_re.match(text, m.end())
                    kind = k.group(1) if k else None
                line = _line_of(line_starts, m.start())
                found.append(Cite(rule, kind, rel, line))
    return found


def _line_of(starts: list[int], pos: int) -> int:
    lo, hi = 0, len(starts)
    while lo < hi:
        mid = (lo + hi) // 2
        if starts[mid] <= pos:
            lo = mid + 1
        else:
            hi = mid
    return lo


def read_allowlist(path: Path) -> list[tuple[str, str, str, int]]:
    """Lines: `rule | reason | iteration that covers it`."""
    out = []
    if not path.exists():
        return out
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = [x.strip() for x in s.split("|")] + ["", ""]
        out.append((parts[0], parts[1], parts[2], i))
    return out


def evidence(cfg: Config) -> tuple[int, int, int, list[str]]:
    """Total tests, failures+errors, skipped, report files read (from JUnit XML)."""
    total = failed = skipped = 0
    files = []
    for g in cfg.junit_globs:
        for p in sorted(cfg.root.glob(g)):
            try:
                root = ET.parse(p).getroot()
            except ET.ParseError:
                continue
            suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
            for s in suites:
                total += int(s.get("tests", 0))
                failed += int(s.get("failures", 0)) + int(s.get("errors", 0))
                skipped += int(s.get("skipped", 0))
            files.append(p.relative_to(cfg.root).as_posix())
    return total, failed, skipped, files


PATH_RE = re.compile(r"`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-*]+)+/?)`")


def stale_spec_paths(cfg: Config) -> list[str]:
    """Paths written in backticks in the spec documents that no longer exist."""
    out = []
    for g in cfg.spec_files:
        for p in sorted(cfg.root.glob(g)):
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                for m in PATH_RE.finditer(line):
                    ref = m.group(1).rstrip("/")
                    if "://" in ref or "<" in ref or ref.startswith(("http", "#")):
                        continue
                    if cfg.path_prefixes and not ref.startswith(tuple(cfg.path_prefixes)):
                        continue
                    hits = list(cfg.root.glob(ref)) if "*" in ref else [cfg.root / ref]
                    if not any(h.exists() for h in hits):
                        out.append(f"{p.relative_to(cfg.root).as_posix()}:{n} references `{ref}`, which does not exist")
    return out


# ---------------------------------------------------------------------------------------------------- checks
def coverage(cfg: Config) -> tuple[dict[str, str], dict[str, list[Cite]]]:
    defined = rules(cfg)
    by_rule: dict[str, list[Cite]] = {r: [] for r in defined}
    for c in citations(cfg):
        by_rule.setdefault(c.rule, []).append(c)
    return defined, by_rule


def check(cfg: Config) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    defined, by_rule = coverage(cfg)
    if not defined:
        errors.append("rules: no rule definitions found; check [rules] files and definition_pattern")
    prefixes = {r.split("-")[0] for r in defined}
    for rule, cites in sorted(by_rule.items()):
        if rule not in defined and rule.split("-")[0] in prefixes:
            for c in cites[:3]:
                errors.append(f"citation: {c.file}:{c.line} cites {rule}, which is not a defined rule (renamed or removed?)")
    allow = read_allowlist(cfg.allowlist_file)
    allowed = {a[0] for a in allow}
    for rule in defined:
        if not by_rule.get(rule) and rule not in allowed:
            errors.append(f"coverage: {rule} ({defined[rule][:60]}) has no test; add one citing {rule}, "
                          f"or get an allowlist entry approved")
    for rule, reason, until, line in allow:
        if rule not in defined:
            errors.append(f"allowlist line {line}: {rule} is not a defined rule; delete it")
        elif by_rule.get(rule):
            errors.append(f"allowlist line {line}: {rule} is covered now; delete the entry (the list only shrinks)")
        if not reason or not until:
            errors.append(f"allowlist line {line}: {rule} needs a reason and the iteration that covers it")
        elif "TODO" in reason or until.upper() == "TBD":
            warnings.append(f"allowlist line {line}: {rule} still has a placeholder reason or iteration")
    for rule, kinds in cfg.require_kinds.items():
        targets = [r for r in defined if fnmatch.fnmatch(r, rule)]
        for r in targets:
            have = {c.kind for c in by_rule.get(r, []) if c.kind}
            missing = [k for k in kinds if k not in have]
            if missing and r not in allowed:
                errors.append(f"kinds: {r} lacks case kinds {missing} (tag a test with `{r}:{missing[0]}`)")
    if cfg.junit_globs:
        total, failed, skipped, files = evidence(cfg)
        if not files:
            errors.append(f"evidence: no test reports matched {cfg.junit_globs}; run the tests first")
        elif total < cfg.min_tests:
            errors.append(f"evidence: only {total} tests ran (minimum {cfg.min_tests}); a test task may have silently run nothing")
        if failed:
            errors.append(f"evidence: {failed} test(s) failed or errored")
        if total and skipped * 5 > total:
            warnings.append(f"evidence: {skipped} of {total} tests were skipped")
    errors += [f"spec: {s}" for s in stale_spec_paths(cfg)]
    return errors, warnings


def matrix(cfg: Config) -> str:
    defined, by_rule = coverage(cfg)
    allowed = {a[0]: a for a in read_allowlist(cfg.allowlist_file)}
    covered = sum(1 for r in defined if by_rule.get(r))
    lines = [
        "# Coverage matrix",
        "",
        f"{MATRIX_MARKER} rules={len(defined)} covered={covered} -->",
        "",
        "Generated by `testguard matrix`; do not edit by hand. A rule is covered when a test cites its ID; "
        "case kinds come from tags such as `RULE-ID:boundary`.",
        "",
        f"Covered **{covered} / {len(defined)}** rules.",
        "",
        "| Rule | Title | Case kinds | Tests | Status |",
        "|---|---|---|---|---|",
    ]
    for r, title in defined.items():
        cites = by_rule.get(r, [])
        kinds = sorted({c.kind for c in cites if c.kind})
        files = sorted({c.file for c in cites})
        shown = "<br>".join(f"`{f}`" for f in files[:4]) + (f"<br>+{len(files) - 4} more" if len(files) > 4 else "")
        status = "covered" if cites else (f"allowlisted ({allowed[r][2]})" if r in allowed else "**MISSING**")
        lines.append(f"| {r} | {title.replace('|', '/')} | {', '.join(kinds) or '-'} | {shown or '-'} | {status} |")
    return "\n".join(lines) + "\n"


def drift(cfg: Config) -> dict:
    """What changed since the matrix file was written: new/removed rules, coverage lost or gained."""
    defined, by_rule = coverage(cfg)
    old_rules: set[str] = set()
    old_covered: set[str] = set()
    if cfg.matrix_file.exists():
        for line in cfg.matrix_file.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\|\s*(\S+)\s*\|.*\|\s*([^|]+?)\s*\|\s*$", line)
            if m and m.group(1) not in {"Rule", "---"}:
                old_rules.add(m.group(1))
                if m.group(2) == "covered":
                    old_covered.add(m.group(1))
    now_covered = {r for r in defined if by_rule.get(r)}
    errors, warnings = check(cfg)
    return {
        "version": VERSION,
        "matrix_found": cfg.matrix_file.exists(),
        "rules": len(defined),
        "covered": len(now_covered),
        "new_rules": sorted(set(defined) - old_rules) if old_rules else [],
        "removed_rules": sorted(old_rules - set(defined)),
        "coverage_lost": sorted(old_covered - now_covered),
        "coverage_gained": sorted(now_covered - old_covered) if old_rules else [],
        "check_errors": errors,
        "check_warnings": warnings,
        "matrix_outdated": cfg.matrix_file.exists() and cfg.matrix_file.read_text(encoding="utf-8") != matrix(cfg),
    }


def init(cfg: Config, baseline: bool) -> int:
    if not baseline:
        print("testguard init: nothing to scaffold without --baseline; write testguard.toml from the template")
        return 0
    defined, by_rule = coverage(cfg)
    existing = {a[0] for a in read_allowlist(cfg.allowlist_file)}
    new = [r for r in defined if not by_rule.get(r) and r not in existing]
    cfg.allowlist_file.parent.mkdir(parents=True, exist_ok=True)
    with cfg.allowlist_file.open("a", encoding="utf-8") as f:
        if not existing:
            f.write("# Rules without a test today. rule | reason | iteration that covers it. The list only shrinks.\n")
        for r in new:
            f.write(f"{r} | TODO reason | TBD\n")
    print(f"appended {len(new)} uncovered rules to {cfg.allowlist_file.relative_to(cfg.root)}; fill in every reason")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="testguard", description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["check", "matrix", "drift", "init", "version"])
    ap.add_argument("--config", default="testguard.toml")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    args = ap.parse_args(argv)
    if args.command == "version":
        print(VERSION)
        return 0
    cfg = load_config(Path(args.config).resolve())
    if args.command == "check":
        errors, warnings = check(cfg)
        for w in warnings:
            print("warning:", w, file=sys.stderr)
        for e in errors:
            print("error:", e)
        print(f"testguard {VERSION}: {'FAILED' if errors else 'OK'} ({len(errors)} error(s))")
        return 1 if errors else 0
    if args.command == "matrix":
        text = matrix(cfg)
        out = Path(args.out).resolve() if args.out else cfg.matrix_file
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
        return 0
    if args.command == "drift":
        d = drift(cfg)
        if args.json:
            print(json.dumps(d, indent=2))
        else:
            for k, v in d.items():
                print(f"{k}: {v}")
        return 0
    return init(cfg, args.baseline)


if __name__ == "__main__":
    sys.exit(main())
