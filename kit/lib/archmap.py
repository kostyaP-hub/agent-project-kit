"""ctx-archmap — render/write a compact ARCHITECTURE.md from Layer A facts (spec v2 §Q2).

Provenance-split: ⚙️ sections are generated from the fact of code (never hand-edited),
🧠 sections are small TODO slots for human intent. The map embeds a compact anchor
block (signature_hash + counts + git source) so a linter can re-derive the signature
from the code and catch drift deterministically (the gate is STATELESS — it compares
code to the signature embedded in the map, no sidecar lock). The whole rendered text
passes through X3 redaction as a final belt-and-suspenders.
"""
import hashlib
import json
import os
import subprocess

from lib.extract import scan_repo
from lib.redact import redact_value

GENERATOR_VERSION = "0.1.0"
ANCHOR_SCHEMA_VERSION = 1

# facts that define the STRUCTURAL signature (change => regenerate / drift alarm).
# formatting/comment/body edits do not touch these, so the signature is stable to noise.
# git sha / dirty are provenance METADATA, NOT signature material (else every commit flips it).
_SIGNATURE_KEYS = (
    "entry_points", "routes", "fsm_candidates", "contracts",
    "packages", "modules", "db_tables", "commands",
)

DEFAULT_MAP_NAME = "ARCHITECTURE.md"
HOOKUP_LINE = f"@./{DEFAULT_MAP_NAME}"


def build_anchors(facts):
    """Full machine-checkable inventory + a stable structural signature hash."""
    counts = {k: len(facts[k]) for k in _SIGNATURE_KEYS}
    material = {k: facts[k] for k in _SIGNATURE_KEYS}
    material["counts"] = counts
    sig = hashlib.sha256(
        json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "anchor_schema_version": ANCHOR_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "signature_hash": sig,
        "counts": counts,
        "config_files": facts["config_files"],
        "unsupported": facts["unsupported"],
        **material,
    }


def rendered_counts(anchors, facts):
    """Counts exactly as they appear in the map header — ONE representation, shared
    by the renderer and the drift gate.

    Two spellings of the same numbers is how a gate starts reporting fields that
    never changed: the header wrote `fsm=` and `db_tables=n/a` while the gate
    compared `fsm_candidates` and an int, so every stale report listed both as
    changed (`[None, 0]`) regardless of the actual drift.
    """
    c = anchors["counts"]
    return {
        "packages": c["packages"],
        "modules": c["modules"],
        "entry_points": c["entry_points"],
        "routes": c["routes"],
        "fsm": c["fsm_candidates"],
        "contracts": c["contracts"],
        # F4 honesty: "n/a" (detector not applicable) is not the number 0.
        "db_tables": c["db_tables"] if facts.get("orm_detected") else "n/a",
        "commands": c["commands"],
    }


def _counts_line(anchors, facts):
    return " ".join(f"{k}={v}" for k, v in rendered_counts(anchors, facts).items())


def _git_provenance(root):
    def _git(*args):
        try:
            r = subprocess.run(["git", "-C", root, *args],
                               capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    sha = _git("rev-parse", "--short=7", "HEAD")
    if not sha:
        return None
    return {"branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "?",
            "sha": sha, "dirty": bool(_git("status", "--porcelain"))}


def _source_str(prov):
    if not prov:
        return "(not a git repo)"
    return f"{prov['branch']} @ {prov['sha']}" + (", dirty" if prov["dirty"] else "")


def _bullets(items, empty="(none detected)"):
    return "\n".join(f"- {i}" for i in items) if items else empty


def _route_prefix(route, depth=2):
    """Group key = up to the first `depth` path segments (e.g. '/api/mkt')."""
    path = route.split(" ", 1)[1] if " " in route else route
    segs = [s for s in path.split("/") if s]
    return "/" + "/".join(segs[:depth]) if segs else "/"


def _group_routes(routes, depth=2):
    """Group 'VERB /path' routes by path prefix so a route-monolith map navigates.

    Render-only (F7): the route inventory and the signature_hash are unchanged —
    grouping is layout, not fact. Trial: 107/120 routes in one main.py read as a
    flat wall; the human CODE_MAP navigates them by prefix, so the map should too.
    """
    groups = {}
    for r in routes:
        groups.setdefault(_route_prefix(r, depth), []).append(r)
    return [(k, groups[k]) for k in sorted(groups)]


def _auth_tag(route, public_paths, public_prefixes):
    """F8: '[public]' if the route path is in the repo's literal allowlist, else '[auth]'."""
    path = route.split(" ", 1)[1] if " " in route else route
    if path in public_paths or any(path.startswith(p) for p in public_prefixes):
        return " [public]"
    return " [auth]"


def _module_section(packages, modules):
    """§2 tier map: modules grouped under their package (P4-1, module-monolith analog
    of F7). Old §2 listed bare package names; a module-monolith (one package, dozens
    of modules) rendered as one opaque line. Group by package so the map navigates.
    Grouped by the code hierarchy (packages), not name-prefix — on a real monolith
    most name-prefixes are singletons, so prefix clustering is noise.
    """
    if not packages:
        return "(flat layout — no sub-packages)"
    by_pkg = {}
    for m in modules:
        pkg, _, stem = m.rpartition(".")
        by_pkg.setdefault(pkg, []).append(stem)
    lines = []
    for pkg in packages:  # authoritative + already sorted; empty packages show (0)
        mods = sorted(by_pkg.get(pkg, []))
        lines.append(f"`{pkg}` ({len(mods)}):")
        lines.extend(f"- {s}" for s in mods)
    return "\n".join(lines)


def _routes_section(routes, auth=None):
    """Render routes grouped by path prefix; full 'VERB /path' inventory preserved.

    `auth` = (public_paths, public_prefixes) when auth-tier is opted in (F8); each
    route is tagged [public]/[auth]. Tagging is layout only — the inventory and
    signature are unchanged."""
    if not routes:
        return "(none detected)"
    lines = []
    for prefix, rs in _group_routes(routes):
        lines.append(f"`{prefix}` ({len(rs)}):")
        for r in rs:
            tag = _auth_tag(r, *auth) if auth else ""
            lines.append(f"- {r}{tag}")
    return "\n".join(lines)


def _provenance_lines(prov, show):
    """Provenance describes the GENERATION EVENT, not the architecture.

    It belongs on a map that travels (stdout preview, vault sync, pasted into a
    chat) — there, "which ref is this?" is unanswerable otherwise. A map committed
    to git must NOT carry it: git already records the commit, and a branch name
    baked into the file becomes a lie the moment the branch is squash-merged
    (`Source: feat/x` sitting in main). It is also per-branch churn on the exact
    two lines every concurrent PR would touch.
    """
    if not show:
        return "", ""
    src = _source_str(prov)
    return f"> Source: {src}\n", f"source: {src}\n"


def _render_md(facts, anchors, name, prov, show_provenance=True):
    fsm_lines = "\n".join(f"- `{k}`: {', '.join(v)}" for k, v in facts["fsm_candidates"].items())
    roles = "\n".join(f"- `{p}` — TODO: one-line responsibility" for p in facts["packages"]) \
        or "- TODO: name the main components and their jobs"
    unsupported = ""
    if facts["unsupported"]:
        unsupported = "\n> ⚠️ Not analyzed (outside v1 language matrix / router prefix): " + ", ".join(facts["unsupported"])
    src_line, src_anchor = _provenance_lines(prov, show_provenance)
    orm = facts.get("orm_detected", False)
    # honesty (F4): distinguish "scanned, empty" from "detector not applicable"
    tables_note = (", ".join(facts["db_tables"]) or "(none)") if orm \
        else "n/a — no ORM detected (raw-SQL/asyncpg not covered)"
    fsm_head = ", ".join(facts["fsm_candidates"]) or "(none detected — Enum-based only)"
    auth = (set(facts.get("public_paths", [])), facts.get("public_prefixes", [])) \
        if facts.get("auth_tier_active") else None
    md = f"""# Architecture — {name}

{src_line}> Auto-generated skeleton (ctx-archmap {GENERATOR_VERSION}). ⚙️ = from code fact, do NOT hand-edit. 🧠 = human intent, fill the TODOs.

## 1. What it is  🧠
<!-- TODO: 1–3 lines — the problem this solves, not the tech. -->

## 2. Tiers / module map  ⚙️
{_module_section(facts["packages"], facts["modules"])}

## 3. Roles / agents  🧠
{roles}

## 4. Entry points  ⚙️
{_bullets(facts["entry_points"])}

## 5. Contracts / API surface  ⚙️
Routes:
{_routes_section(facts["routes"], auth)}
Models:
{_bullets(facts["contracts"])}
Tables: {tables_note}

## 6. State machine (FSM)  🧠
Candidates (from Enums): {fsm_head}
{fsm_lines}
<!-- TODO: name the canonical lifecycle, if any. -->

## 7. Boundaries — Always / Ask / Never  🧠  (highest-value section)
<!-- TODO:
Always: ...
Ask:    ...
Never:  ... -->

## 8. Commands  ⚙️
{_bullets(facts["commands"], "(none detected — Makefile / scripts/ / *.sh / package.json)")}

## 9. Known drift / decisions  🧠
<!-- TODO: open tech-debt + → ADR/MADR links -->{unsupported}

<!-- ctx-archmap:anchors
{src_anchor}signature_hash: {anchors["signature_hash"]}
generator_version: {GENERATOR_VERSION}
counts: {_counts_line(anchors, facts)}
-->
"""
    return redact_value(md)


def render_architecture(root, project_name=None,
                        auth_public_const=None, auth_public_prefix_const=None):
    """Render the ARCHITECTURE.md text for a repo (deterministic + redacted).

    auth_public_const/auth_public_prefix_const (F8, opt-in): resolved from
    ~/.ctx/config.json by the CLI and threaded here for auth-tier tagging."""
    root = os.path.abspath(os.path.expanduser(root))
    facts = scan_repo(root, auth_public_const, auth_public_prefix_const)
    name = project_name or os.path.basename(root)
    return _render_md(facts, build_anchors(facts), name, _git_provenance(root))


def resolve_map_path(root, map_path=None):
    """Absolute path of the map. Default keeps the repo-root convention; `map_path`
    (relative to root, or absolute) lets a repo that already owns a hand-written
    docs/ARCHITECTURE.md put the generated one somewhere unambiguous."""
    if not map_path:
        return os.path.join(root, DEFAULT_MAP_NAME)
    return map_path if os.path.isabs(map_path) else os.path.join(root, map_path)


def _hook_into_agents(root, rel_map=DEFAULT_MAP_NAME):
    """Add `@./<map>` to AGENTS.md so every CLI auto-loads the map. Idempotent.

    Returns "added" | "already" | "no_agents" — one falsy value for both "there is
    no AGENTS.md" and "it is already wired" made the CLI tell people to scaffold a
    file they already had."""
    agents = os.path.join(root, "AGENTS.md")
    if not os.path.exists(agents):
        return "no_agents"
    line = f"@./{rel_map}"
    txt = open(agents, encoding="utf-8").read()
    if line in txt:
        return "already"
    if not txt.endswith("\n"):
        txt += "\n"
    txt += f"\n## Architecture map\n{line}\n"
    open(agents, "w", encoding="utf-8").write(txt)
    return "added"


def write_map(root, project_name=None,
              auth_public_const=None, auth_public_prefix_const=None, map_path=None):
    """Write the map + AGENTS.md hookup. Returns {map, hooked}.

    No sidecar lock: the drift gate is stateless (it re-derives the signature from
    code and compares it to the one embedded in the map), so a lock would only add
    a merge-conflict surface (full route list) with no reader (F6).
    """
    root = os.path.abspath(os.path.expanduser(root))
    facts = scan_repo(root, auth_public_const, auth_public_prefix_const)
    anchors = build_anchors(facts)
    name = project_name or os.path.basename(root)
    dest = resolve_map_path(root, map_path)
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    open(dest, "w", encoding="utf-8").write(
        # committed file => no provenance (see _provenance_lines)
        _render_md(facts, anchors, name, None, show_provenance=False))
    return {"map": dest, "hooked": _hook_into_agents(root, os.path.relpath(dest, root))}
