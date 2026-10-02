#!/usr/bin/env python3
"""ctx-lint — проверка инженерного контекста репозитория.

Проверяет:
  - AGENTS.md существует;
  - все @./rules/*.md (и прочие @-import) резолвятся;
  - нет ${VAR} в project-level @-import (Claude Code их молча игнорирует);
  - CLAUDE.md = тонкая обёртка `@AGENTS.md` (warn если есть лишнее);
  - репо «наш» по git remote (warn если origin чужой / отсутствует).

Usage:
  ctx-lint.py <repo-path>      # один репо
  ctx-lint.py --all            # все AGENTS.md под scan-roots
  ctx-lint.py --all --json     # машинный вывод

Scan-roots и owned namespaces для --all задаются в ~/.ctx/config.json.
"""
import os
import re
import sys
import json
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import lint as _ctxlint  # noqa: E402
from lib.config import load_config  # noqa: E402
from lib.scorecard import build_scorecard, generated_markdown, render_scorecard  # noqa: E402

HOME = os.path.expanduser("~")
_CFG = load_config()  # config-as-data (~/.ctx/config.json, spec §Q3) — no hardcode
SCAN_ROOTS = _CFG["scan_roots"]
OWNED = tuple(_CFG["owned"])
_EXCLUDED = set(_CFG["excluded_paths"])


def _load_extra_roots():
    """Keep the extra-root boundary available to discovery.

    ``load_config`` intentionally returns one combined scan list for callers
    that do not care about traversal.  Fleet discovery does care: an extra
    root can itself be a repository, and nested extra roots must not cause the
    parent to recurse into the child a second time.
    """
    path = os.path.join(HOME, ".ctx", "config.json")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    roots = data.get("extra_roots", [])
    return [os.path.abspath(os.path.expanduser(root)) for root in roots if isinstance(root, str)]


EXTRA_ROOTS = _load_extra_roots()
IMPORT_RE = re.compile(r"^\s*@(.+?)\s*$")
FORBIDDEN_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "config", "forbidden-lines.json")
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
PUSH_GATE_RE = re.compile(r"спрос|после\s+ОК|approval|по\s+просьб|--force|force-push|никогда|запрещ|нельзя|не\s+делай|forbidden|never|только\s+по", re.IGNORECASE)
PUSH_PROHIBITION_RE = re.compile(r"(?:не\s+делай|never|никогда|без\s+(?:явной\s+)?просьб)", re.IGNORECASE)


def load_forbidden_rules():
    """Read forbidden instruction-line rules; invalid local config fails loudly."""
    with open(FORBIDDEN_CONFIG, encoding="utf-8") as f:
        rules = json.load(f)
    for rule in rules:
        if set(rule) != {"id", "pattern", "severity", "message", "exception_marker"}:
            raise ValueError(f"invalid forbidden rule shape: {rule!r}")
        if rule["severity"] not in {"error", "warn"}:
            raise ValueError(f"invalid forbidden severity: {rule['id']}")
        re.compile(rule["pattern"])
        re.compile(rule["exception_marker"])
    return rules


FORBIDDEN_RULES = load_forbidden_rules()


def _instruction_paths(repo):
    for name in INSTRUCTION_FILES:
        path = os.path.join(repo, name)
        if os.path.isfile(path):
            yield path
    rules = os.path.join(repo, "rules")
    if os.path.isdir(rules):
        for name in sorted(os.listdir(rules)):
            path = os.path.join(rules, name)
            if name.endswith(".md") and os.path.isfile(path):
                yield path


def _is_unmodified_universal_rule(path):
    """The bundled rules describe prohibitions; an exact locked copy is not drift."""
    source = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "rules", os.path.basename(path))
    try:
        return os.path.samefile(path, source) or open(path, "rb").read() == open(source, "rb").read()
    except OSError:
        return False


def _documented_exception(lines, lineno, rule):
    marker = re.compile(rule["exception_marker"])
    return any(marker.search(line) for line in lines[max(0, lineno - 4):lineno - 1])


def forbidden_issues(repo):
    """Return (violations, documented exceptions) from agent instruction files."""
    issues, exceptions = [], []
    for path in _instruction_paths(repo):
        if _is_unmodified_universal_rule(path):
            continue
        lines = open(path, encoding="utf-8").read().splitlines()
        text = "\n".join(lines)
        for rule in FORBIDDEN_RULES:
            pattern = re.compile(rule["pattern"])
            for match in pattern.finditer(text):
                lineno = text.count("\n", 0, match.start()) + 1
                # A push gate may be on the matching line or in either two-line direction.
                context = "\n".join(lines[max(0, lineno - 3):min(len(lines), lineno + 2)])
                if (rule["id"] == "push-without-gate"
                        and (PUSH_GATE_RE.search(context) or PUSH_PROHIBITION_RE.search(context))):
                    continue
                item = {"id": rule["id"], "severity": rule["severity"], "message": rule["message"],
                        "path": path, "line": lineno}
                if _documented_exception(lines, lineno, rule):
                    exceptions.append(item)
                else:
                    issues.append(item)
    return issues, exceptions


def _scorecard_with_forbidden(rows, repos):
    counts = {}
    for repo in repos:
        issues, _ = forbidden_issues(repo)
        counts[os.path.abspath(repo)] = len(issues)
    for row in rows:
        row["forbidden"] = counts.get(os.path.abspath(row["path"]), 0)
    return rows


def _render_scorecard_with_forbidden(rows):
    """Keep the library scorecard intact while extending this CLI's table."""
    lines = render_scorecard(rows).splitlines()
    lines[0] = lines[0][:-1] + "| forbidden |"
    lines[1] += "---|"
    for i in range(2, len(lines)):
        lines[i] = lines[i][:-1] + f"| {rows[i - 2]['forbidden']} |"
    return "\n".join(lines)


def _generated_scorecard_with_forbidden(rows):
    table = _render_scorecard_with_forbidden(rows)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return (f"%% AUTO-GENERATED by ctx-lint --scorecard · built {timestamp} · do not edit %%\n\n"
            f"{table}\n")


def git_remote_ns(repo):
    if not os.path.isdir(os.path.join(repo, ".git")):
        return None
    try:
        r = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    m = re.search(r"[/:]([^/]+)/[^/]+?(?:\.git)?\s*$", r.stdout.strip())
    return m.group(1).lower() if m else None


def parse_imports(agents):
    out = []
    for i, line in enumerate(open(agents, encoding="utf-8"), 1):
        m = IMPORT_RE.match(line)
        if m and not m.group(1).startswith(("AGENTS.md",)):
            out.append((i, m.group(1).strip()))
    return out


def check(repo, mode="warn"):
    rep = {"repo": repo, "status": "ok", "issues": [], "exceptions": [], "forbidden": 0,
           "imports_ok": 0, "imports_total": 0}
    forbidden, exceptions = forbidden_issues(repo)
    rep["forbidden"] = len(forbidden)
    rep["exceptions"] = exceptions
    for item in forbidden:
        # warn mode is an adoption phase: configured errors are visible but non-blocking.
        severity = "warn" if mode == "warn" and item["severity"] == "error" else item["severity"]
        rep["issues"].append((severity, f"{item['path']}:{item['line']}: [{item['id']}] {item['message']}"))
    agents = os.path.join(repo, "AGENTS.md")
    if not os.path.exists(agents):
        rep["status"] = "error"
        rep["issues"].append(("error", "AGENTS.md отсутствует"))
        return rep
    # context-standard checks are advisory by default; --mode=block escalates them.
    new_sev = "error" if mode == "block" else "warn"

    # ownership
    ns = git_remote_ns(repo)
    if ns is not None and not any(ns.startswith(o) for o in OWNED):
        rep["issues"].append(("warn", f"origin namespace '{ns}' не в OWNED — возможно чужой клон, не писать"))

    # imports
    for lineno, raw in parse_imports(agents):
        rep["imports_total"] += 1
        if "${" in raw:
            rep["issues"].append(("error", f"line {lineno}: ${{...}} в @-import молча игнорируется Claude Code: @{raw}"))
            continue
        if raw.startswith("~"):
            target = os.path.expanduser(raw)
        elif raw.startswith("/"):
            target = raw
        else:
            target = os.path.join(repo, raw[2:] if raw.startswith("./") else raw)
        if os.path.exists(target):
            rep["imports_ok"] += 1
        else:
            rep["issues"].append(("error", f"line {lineno}: @{raw} -> файл не найден ({target})"))

    # CLAUDE.md thin wrapper
    claude = os.path.join(repo, "CLAUDE.md")
    if os.path.exists(claude):
        if not _is_agents_wrapper(claude, agents):
            rep["issues"].append(("warn", "CLAUDE.md не импортит @AGENTS.md (Codex/Gemini читают AGENTS.md)"))

    # universal rules drift (content-hash lock)
    if os.path.isdir(os.path.join(repo, "rules")):
        for fn, kind in _ctxlint.check_rules_drift(repo):
            rep["issues"].append((new_sev, f"rules/{fn}: {kind} vs источник (universal-locked)"))

    # GEMINI.md presence and thin wrapper (cross-CLI single-source)
    gemini = os.path.join(repo, "GEMINI.md")
    if not os.path.exists(gemini):
        rep["issues"].append((new_sev, "GEMINI.md отсутствует (Gemini CLI не получит правила)"))
    elif not _is_agents_wrapper(gemini, agents):
        rep["issues"].append(("warn", "GEMINI.md не тонкая обёртка: перенеси правила в AGENTS.md"))

    # load_strategy frontmatter validity
    bad_strategy = _ctxlint.check_load_strategy(repo)
    if bad_strategy:
        rep["issues"].append(
            (new_sev, f"load_strategy '{bad_strategy}' невалиден (ожидается alpha|orchestrator|symlink-consumer)"))

    # config/*.json validate-only vs companion *.schema.json
    for name, err in _ctxlint.check_config(repo):
        rep["issues"].append((new_sev, f"config/{name}: {err}"))

    # ARCHITECTURE.md freshness (only flagged if a map exists; missing map = opt-in)
    am = _ctxlint.check_archmap(repo)
    if am["status"] == "stale":
        rep["issues"].append(
            (new_sev, f"ARCHITECTURE.md устарела ({am['found']}≠{am['expected']}); changed: {am.get('changed')}"))
    elif am["status"] == "no_anchor":
        rep["issues"].append(("warn", "ARCHITECTURE.md без ctx-archmap signature-anchor"))

    sev = {s for s, _ in rep["issues"]}
    rep["status"] = "error" if "error" in sev else ("warn" if "warn" in sev else "ok")
    return rep


def _is_agents_wrapper(path, agents):
    """Whether a wrapper imports AGENTS.md or is a symlink to it."""
    try:
        if os.path.samefile(path, agents):
            return True
        meaningful = [line.strip() for line in open(path, encoding="utf-8")
                      if line.strip() and not line.strip().startswith("<!--")]
    except OSError:
        return False
    return meaningful and all(line in {"@AGENTS.md", "@./AGENTS.md"} for line in meaningful)


def _is_discoverable_repo(path):
    return (os.path.isdir(path)
            and (os.path.exists(os.path.join(path, ".git"))
                 or any(os.path.exists(os.path.join(path, name)) for name in INSTRUCTION_FILES)))


def _has_nested_extra_root(root):
    root = os.path.realpath(root)
    for extra in EXTRA_ROOTS:
        extra = os.path.realpath(extra)
        if extra != root and os.path.commonpath((root, extra)) == root:
            return True
    return False


def discover():
    found = set()
    for root in SCAN_ROOTS:
        if not os.path.isdir(root):
            continue
        root = os.path.abspath(root)
        # Extra roots may point directly at a repository, unlike the original
        # workspace scan roots that enumerate their immediate children.
        if root in EXTRA_ROOTS and _is_discoverable_repo(root):
            found.add(root)
        # A parent extra root (for example ~/.claude) owns only itself when a
        # nested extra root (~/.claude/skills) handles the child traversal.
        if _has_nested_extra_root(root):
            continue
        for name in os.listdir(root):
            d = os.path.join(root, name)
            if d in _EXCLUDED:
                continue
            if _is_discoverable_repo(d):
                found.add(d)
    return sorted(found)


def main():
    argv = sys.argv[1:]
    json_target = None
    md_target = None
    paths = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--json", "--write-md"):
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                if arg == "--json":
                    json_target = argv[i + 1]
                else:
                    md_target = argv[i + 1]
                i += 2
                continue
        if not arg.startswith("--"):
            paths.append(arg)
        i += 1
    json_mode = "--json" in argv
    if "--all" in argv:
        if not SCAN_ROOTS:
            print("SCAN_ROOTS не заданы: добавь scan_roots в ~/.ctx/config.json")
            return 2
        repos = discover()
    elif paths:
        repos = [os.path.abspath(os.path.expanduser(paths[0]))]
    else:
        print(__doc__)
        return 2

    if "--scorecard" in argv:
        rows = _scorecard_with_forbidden(build_scorecard(repos, OWNED), repos)
        markdown = _render_scorecard_with_forbidden(rows)
        if json_target:
            with open(json_target, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
                f.write("\n")
        if md_target:
            with open(md_target, "w", encoding="utf-8") as f:
                f.write(_generated_scorecard_with_forbidden(rows))
        print(markdown)
        return 0

    mode = "warn"  # audit=report-only exit0 | warn=new checks advisory | block=new checks error
    for a in argv:
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
    reports = [check(r, mode) for r in repos]
    if json_mode:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 0 if mode == "audit" else (1 if any(r["status"] == "error" for r in reports) else 0)

    errs = warns = 0
    for r in reports:
        em = {"ok": "OK", "warn": "WARN", "error": "ERR"}[r["status"]]
        print(f"[{em}] {r['repo']}  ({r['imports_ok']}/{r['imports_total']} @-imports)")
        for sev, msg in r["issues"]:
            print(f"      {sev.upper()}: {msg}")
            if sev == "error":
                errs += 1
            else:
                warns += 1
        for item in r["exceptions"]:
            print(f"      {item['path']}:{item['line']}: [{item['id']}] exception (documented)")
    print(f"\n{len(reports)} репо: {errs} errors, {warns} warnings  (mode={mode})")
    return 0 if mode == "audit" else (1 if errs else 0)


if __name__ == "__main__":
    sys.exit(main())
