"""Lint checks for the context standard (spec v2 §X1/Verify).

`check_archmap` is the deterministic drift gate: re-derive the structural
signature from the actual code and compare it to the one embedded in
ARCHITECTURE.md. Formatting/body edits do not move the signature (facts, not
source text, are hashed), so this flags real architectural drift only.
"""
import hashlib
import json
import os
import re

from lib.archmap import build_anchors, rendered_counts, resolve_map_path
from lib.extract import scan_repo

_SIG_RE = re.compile(r"signature_hash:\s*([0-9a-f]+)")
_COUNTS_RE = re.compile(r"counts:\s*(.+)")

# Rules that MUST be byte-identical everywhere (locked to the single source).
UNIVERSAL_RULES = ("auth-payments.md", "commits.md", "git.md", "secrets.md", "worktree.md")
# stack/testing/boundaries/focus are per-project and intentionally NOT locked.
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RULES_SRC = os.path.join(_SKILL_ROOT, "rules")


def _normalize(text):
    """Strip trailing whitespace / surrounding blank lines so noise isn't drift."""
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _content_hash(text):
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


_VAULT_RE = re.compile(r"^vault_entity:\s*(\S+)", re.MULTILINE)


def read_vault_entity(root):
    """Return the `vault_entity:` slug from AGENTS.md frontmatter (repo↔vault bridge)."""
    agents = os.path.join(os.path.abspath(os.path.expanduser(root)), "AGENTS.md")
    if not os.path.exists(agents):
        return None
    m = _VAULT_RE.search(open(agents, encoding="utf-8").read())
    return m.group(1).strip("\"'") if m else None


_SCORECARD_DIMS = ("agents", "rules", "gemini", "legibility", "vault")


def scorecard_row(repo):
    """Per-repo coverage of the context standard's dimensions."""
    root = os.path.abspath(os.path.expanduser(repo))
    rules_ok = os.path.isdir(os.path.join(root, "rules")) and not check_rules_drift(root)
    return {
        "agents": os.path.exists(os.path.join(root, "AGENTS.md")),
        "rules": rules_ok,
        "gemini": os.path.exists(os.path.join(root, "GEMINI.md")),
        "legibility": check_archmap(root)["status"] == "ok",
        "vault": bool(read_vault_entity(root)),
    }


def render_scorecard(repos):
    """Markdown coverage table across repos — observable, not asserted (spec §Q4)."""
    head = "| repo | " + " | ".join(_SCORECARD_DIMS) + " |"
    sep = "|" + "---|" * (len(_SCORECARD_DIMS) + 1)
    lines = [head, sep]
    for repo in repos:
        row = scorecard_row(repo)
        cells = ["✓" if row[d] else "✗" for d in _SCORECARD_DIMS]
        lines.append(f"| {os.path.basename(os.path.normpath(repo))} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


VALID_LOAD_STRATEGIES = {"alpha", "orchestrator", "symlink-consumer"}
_STRATEGY_RE = re.compile(r"^load_strategy:\s*(\S+)", re.MULTILINE)


def check_load_strategy(root):
    """Return the invalid load_strategy value from AGENTS.md, or None if ok/absent."""
    agents = os.path.join(os.path.abspath(os.path.expanduser(root)), "AGENTS.md")
    if not os.path.exists(agents):
        return None
    m = _STRATEGY_RE.search(open(agents, encoding="utf-8").read())
    if m:
        val = m.group(1).strip("\"'")
        if val not in VALID_LOAD_STRATEGIES:
            return val
    return None


def _type_ok(val, jtype):
    if jtype == "integer":
        return isinstance(val, int) and not isinstance(val, bool)
    if jtype == "number":
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    py = {"string": str, "boolean": bool, "array": list,
          "object": dict, "null": type(None)}.get(jtype)
    return py is None or isinstance(val, py)


def check_config(root):
    """Validate-only for config/*.json vs companion *.schema.json (spec §Q3).

    Deliberately lightweight (no jsonschema dep): JSON parses + required-keys +
    top-level type check. Repair is a separate offline step, NEVER in the lint
    (critic: LLM/auto-repair in a blocking gate = unreviewed mutation).
    """
    cfgdir = os.path.join(os.path.abspath(os.path.expanduser(root)), "config")
    if not os.path.isdir(cfgdir):
        return []
    out = []
    for name in sorted(os.listdir(cfgdir)):
        if not name.endswith(".json") or name.endswith(".schema.json"):
            continue
        try:
            data = json.load(open(os.path.join(cfgdir, name), encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            out.append((name, f"невалидный JSON: {e}"))
            continue
        schema_p = os.path.join(cfgdir, name[:-len(".json")] + ".schema.json")
        if not os.path.exists(schema_p):
            continue
        try:
            schema = json.load(open(schema_p, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for k in schema.get("required", []):
            if not (isinstance(data, dict) and k in data):
                out.append((name, f"нет required-ключа '{k}'"))
        if isinstance(data, dict):
            for k, spec in schema.get("properties", {}).items():
                if k in data and "type" in spec and not _type_ok(data[k], spec["type"]):
                    out.append((name, f"'{k}' не тип {spec['type']}"))
    return out


def check_rules_drift(root, source_dir=None):
    """Return [(filename, 'missing'|'drift')] for universal rules that diverged."""
    source_dir = source_dir or DEFAULT_RULES_SRC
    repo_rules = os.path.join(os.path.abspath(os.path.expanduser(root)), "rules")
    out = []
    for fn in UNIVERSAL_RULES:
        src, dst = os.path.join(source_dir, fn), os.path.join(repo_rules, fn)
        if not os.path.exists(dst):
            out.append((fn, "missing"))
            continue
        if not os.path.exists(src):
            continue
        if _content_hash(open(dst, encoding="utf-8").read()) != \
                _content_hash(open(src, encoding="utf-8").read()):
            out.append((fn, "drift"))
    return out


def read_embedded_signature(md):
    m = _SIG_RE.search(md)
    return m.group(1) if m else None


def read_embedded_counts(md):
    m = _COUNTS_RE.search(md)
    out = {}
    if m:
        for tok in m.group(1).split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                try:
                    out[k] = int(v)
                except ValueError:
                    out[k] = v  # e.g. db_tables=n/a — keep the rendered form verbatim
    return out


def check_archmap(root, map_path=None):
    """Compare the map's embedded signature against a fresh derivation from code."""
    root = os.path.abspath(os.path.expanduser(root))
    md_path = resolve_map_path(root, map_path)
    if not os.path.exists(md_path):
        return {"status": "missing", "map": md_path}
    md = open(md_path, encoding="utf-8").read()
    found = read_embedded_signature(md)
    if not found:
        return {"status": "no_anchor", "map": md_path}
    facts = scan_repo(root)
    anchors = build_anchors(facts)
    current = anchors["signature_hash"]
    if found == current:
        return {"status": "ok", "signature": current, "map": md_path}
    # Compare like for like: both sides in the header's rendered form, or the gate
    # reports fields that never moved (see rendered_counts docstring).
    old, new = read_embedded_counts(md), rendered_counts(anchors, facts)
    changed = {k: [old.get(k), new.get(k)] for k in new if old.get(k) != new.get(k)}
    return {"status": "stale", "found": found, "expected": current,
            "changed": changed, "map": md_path}
