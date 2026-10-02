"""Layer A — deterministic fact extraction from a repo (spec v2 §Q2).

Structure comes from the FACT of code via the stdlib `ast` module — no LLM, no
heavy deps. Given the same source, the same facts come out. Python is the v1
language matrix; anything else is recorded in `unsupported` and never asserted
as fact. JS/tree-sitter is an optional later extension.

File inventory is taken from **git** (`git ls-files`, an allowlist that honors
.gitignore for free) so untracked scratch does not leak into the map or flip the
signature. IGNORE_DIRS / os.walk is only the fallback for non-git dirs. (F1)
"""
import ast
import json
import os
import sys
import re
import subprocess
import tomllib

try:
    import pathspec  # опционально: нужен только для .ctxignore (gitignore-синтаксис)
except ImportError:  # без него работает всё, кроме исключений из .ctxignore
    pathspec = None

from lib.redact import redact_filenames

IGNORE_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules", "build",
    "dist", ".pytest_cache", ".mypy_cache", ".ctx-cache", ".worktrees",
    ".idea", ".vscode", ".eggs", "site-packages", ".tox",
}
# Test scaffolding is excluded from the legibility map — a map describes the
# product's structure, not its test doubles (keeps the map small + honest).
TEST_DIRS = {"tests", "test", "testing"}
HTTP_VERBS = {"get", "post", "put", "delete", "patch", "options", "head"}
ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "IntFlag", "Flag"}
CONTRACT_BASES = {"BaseModel", "TypedDict"}
CONFIG_EXTS = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}
_MAKE_TARGET = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_.\-]*):")


def _is_test_file(base):
    return base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py"


def _load_ignore(root):
    """Load a repo-level `.ctxignore` (gitignore syntax) if present."""
    p = os.path.join(root, ".ctxignore")
    if pathspec is None:
        if os.path.exists(p):
            print("предупреждение: .ctxignore не применён — нет пакета pathspec "
                  "(поставить: pip install pathspec)", file=sys.stderr)
        return None
    if os.path.exists(p):
        try:
            return pathspec.PathSpec.from_lines(
                "gitignore", open(p, encoding="utf-8").read().splitlines())
        except OSError:
            return None
    return None


def _ignored(spec, rel):
    return bool(spec) and (spec.match_file(rel) or spec.match_file(rel + "/"))


def _git_files(root):
    """Tracked files (root-relative) via git — allowlist, honors .gitignore. None if not git."""
    try:
        r = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                           capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    files = [f for f in r.stdout.decode("utf-8", "ignore").split("\0") if f]
    # guard: if paths are not root-relative (root is a subdir edge case), bail to walk
    if files and not any(os.path.exists(os.path.join(root, f)) for f in files[:5]):
        return None
    return files


def _list_files(root):
    """Candidate rel paths: git-tracked (allowlist) else os.walk; IGNORE_DIRS + .ctxignore backstop."""
    ignore = _load_ignore(root)
    tracked = _git_files(root)
    if tracked is not None:
        rels = tracked
    else:
        rels = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            for fn in filenames:
                rels.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))
    out = []
    for rel in rels:
        parts = rel.split("/")
        if any(p in IGNORE_DIRS for p in parts[:-1]):
            continue
        if _ignored(ignore, rel):
            continue
        out.append(rel)
    return out


def _base_names(cls):
    out = set()
    for b in cls.bases:
        if isinstance(b, ast.Name):
            out.add(b.id)
        elif isinstance(b, ast.Attribute):
            out.add(b.attr)
    return out


def _is_main_guard(test):
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _has_router_prefix(tree):
    """True if the module builds/includes a router WITH a prefix= — then decorator
    paths are relative to that prefix and cannot be trusted verbatim (F2)."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = n.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if name in ("APIRouter", "include_router") and any(kw.arg == "prefix" for kw in n.keywords):
                return True
    return False


def _literal_str_elements(node):
    """String constants from a set/list/tuple literal or frozenset(...)/set(...) call.
    Used for F8 auth-tier: PUBLIC_PATHS = frozenset({...}) / PUBLIC_PREFIXES = (...)."""
    if isinstance(node, ast.Call):
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
        if name in ("frozenset", "set", "tuple", "list", "frozen") and node.args:
            node = node.args[0]
        else:
            return None
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return [e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return None


def _routes_from_decorator(dec):
    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
        return []
    attr = dec.func.attr.lower()
    path = None
    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
        path = dec.args[0].value
    if attr in HTTP_VERBS and path:
        return [f"{attr.upper()} {path}"]
    if attr == "route" and path:  # Flask-style: methods in kwarg, default GET
        methods = ["GET"]
        for kw in dec.keywords:
            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                methods = [e.value for e in kw.value.elts
                           if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        return [f"{m.upper()} {path}" for m in methods]
    return []


def _scan_py(src, rel, facts, auth_consts=(None, None)):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        facts["unsupported"].append(rel)
        return
    prefixed = _has_router_prefix(tree)  # honest refusal beats a confident wrong path
    pub_name, pref_name = auth_consts
    # Module-level (top-level scope) constant assignments: F9 MANIFEST contracts +
    # F8 opt-in auth-tier constants (PUBLIC_PATHS / PUBLIC_PREFIXES literals).
    for top in tree.body:
        if not isinstance(top, ast.Assign):
            continue
        for t in top.targets:
            if not isinstance(t, ast.Name):
                continue
            # F9: MANIFEST / *_MANIFEST dict literals are plugin contracts.
            if isinstance(top.value, ast.Dict) and (t.id == "MANIFEST" or t.id.endswith("_MANIFEST")):
                facts["contracts"].add(t.id)
            # F8: literal public-route allowlists (only when opted in via config).
            if pub_name and t.id == pub_name:
                vals = _literal_str_elements(top.value)
                if vals is not None:
                    facts["public_paths"].update(vals)
                    facts["auth_tier_active"] = True
            if pref_name and t.id == pref_name:
                vals = _literal_str_elements(top.value)
                if vals is not None:
                    facts["public_prefixes"].update(vals)
                    facts["auth_tier_active"] = True
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "sqlalchemy":
            facts["orm_detected"] = True
        elif isinstance(node, ast.Import) and any(a.name.split(".")[0] == "sqlalchemy" for a in node.names):
            facts["orm_detected"] = True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not prefixed:
                for dec in node.decorator_list:
                    facts["routes"].update(_routes_from_decorator(dec))
        elif isinstance(node, ast.ClassDef):
            bases = _base_names(node)
            deco = {d.id for d in node.decorator_list if isinstance(d, ast.Name)}
            if bases & ENUM_BASES:
                members = [
                    s.targets[0].id
                    for s in node.body
                    if isinstance(s, ast.Assign)
                    and len(s.targets) == 1
                    and isinstance(s.targets[0], ast.Name)
                    and not s.targets[0].id.startswith("_")
                ]
                facts["fsm_candidates"][node.name] = members
            if bases & CONTRACT_BASES or "dataclass" in deco:
                facts["contracts"].add(node.name)
            for s in node.body:
                if (isinstance(s, ast.Assign) and len(s.targets) == 1
                        and isinstance(s.targets[0], ast.Name)
                        and s.targets[0].id == "__tablename__"
                        and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str)):
                    facts["db_tables"].add(s.value.value)
        elif isinstance(node, ast.If) and _is_main_guard(node.test):
            facts["entry_points"].add(rel)
    if prefixed:
        facts["unsupported"].append(f"{rel} (router prefix — routes не извлечены)")


def scan_repo(root, auth_public_const=None, auth_public_prefix_const=None):
    """Extract deterministic facts from a repo. Returns a dict of sorted inventories.

    auth_public_const / auth_public_prefix_const (F8, opt-in): names of the repo's
    literal public-route constants (e.g. 'PUBLIC_PATHS'). When given and found,
    facts['public_paths']/['public_prefixes'] are populated for render-time
    auth-tier tagging. These are NOT signature material — the gate is unmoved.
    """
    root = os.path.abspath(os.path.expanduser(root))
    facts = {
        "entry_points": set(), "routes": set(), "fsm_candidates": {},
        "contracts": set(), "packages": set(), "db_tables": set(),
        "commands": set(), "config_files": set(), "unsupported": [],
        "orm_detected": False,
        "public_paths": set(), "public_prefixes": set(), "auth_tier_active": False,
        "modules": set(),
    }
    auth_consts = (auth_public_const, auth_public_prefix_const)

    files = _list_files(root)
    # package dirs = dirs with a non-test __init__.py; a module belongs to the
    # tier map (P4-1) only if it lives directly in one (loose scripts are ops,
    # not architectural tiers — they surface as entry_points/commands).
    pkg_dirs = {
        "/".join(rel.split("/")[:-1])
        for rel in files
        if rel.split("/")[-1] == "__init__.py"
        and len(rel.split("/")) > 1
        and not any(p in TEST_DIRS for p in rel.split("/")[:-1])
    }
    for rel in files:
        parts = rel.split("/")
        base = parts[-1]
        in_tests = any(p in TEST_DIRS for p in parts[:-1])
        if base == "__init__.py" and not in_tests and len(parts) > 1:
            facts["packages"].add("/".join(parts[:-1]).replace("/", "."))
        if base.endswith(".py") and not in_tests and not _is_test_file(base):
            parent = "/".join(parts[:-1])
            if base != "__init__.py" and parent in pkg_dirs:  # P4-1: module map
                facts["modules"].add(parent.replace("/", ".") + "." + base[:-3])
            # A package's __main__.py IS the way in (`python -m pkg`) even without
            # an `if __name__ == "__main__"` guard — Cut's raises SystemExit at
            # module level, so the guard-based detector never saw it. Emit the
            # path, not a dotted invocation: under src-layout the dotted form from
            # the repo root is not the importable name (no confidently wrong facts).
            if base == "__main__.py" and parent in pkg_dirs:
                facts["entry_points"].add(rel)
            try:
                src = open(os.path.join(root, rel), encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            _scan_py(src, rel, facts, auth_consts)

    # config surface — root + config/, from the tracked list, redacted (X3)
    cfg = []
    for rel in files:
        parts = rel.split("/")
        if len(parts) == 1 or (len(parts) == 2 and parts[0] == "config"):
            name = parts[-1]
            _, ext = os.path.splitext(name)
            if ext in CONFIG_EXTS or name.startswith(".env"):
                cfg.append(name)
    facts["config_files"] = set(redact_filenames(cfg))

    # pyproject.toml — scripts (entry points)
    pyproject = os.path.join(root, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            data = tomllib.load(open(pyproject, "rb"))
            for v in (data.get("project", {}).get("scripts", {}) or {}).values():
                facts["entry_points"].add(v)
        except (tomllib.TOMLDecodeError, OSError):
            pass

    # package.json — scripts (commands) + bin (entry points)
    pkgjson = os.path.join(root, "package.json")
    if os.path.exists(pkgjson):
        try:
            data = json.load(open(pkgjson, encoding="utf-8"))
            facts["commands"].update((data.get("scripts") or {}).keys())
            b = data.get("bin")
            if isinstance(b, dict):
                facts["entry_points"].update(b.keys())
            elif isinstance(b, str):
                facts["entry_points"].add(b)
        except (json.JSONDecodeError, OSError):
            pass

    # Makefile — targets (commands)
    mk = os.path.join(root, "Makefile")
    if os.path.exists(mk):
        for line in open(mk, encoding="utf-8", errors="ignore"):
            m = _MAKE_TARGET.match(line)
            if m and not m.group(1).startswith("."):
                facts["commands"].add(m.group(1))

    # ops surface — root *.sh + scripts/* (F5: live ops is more than a Makefile)
    for rel in files:
        parts = rel.split("/")
        if len(parts) == 1 and parts[0].endswith(".sh"):
            facts["commands"].add(parts[0])
        elif len(parts) == 2 and parts[0] == "scripts":
            facts["commands"].add(rel)

    # P4-2: a file already surfaced as an ops command is not ALSO an entry point.
    # A scripts/*.py with a __main__ guard was listed twice (Cut: 21 identical
    # lines in §4 and again in §8). It belongs under Commands; §4 answers "how
    # does the product start". Only path-shaped commands dedupe, so a Makefile /
    # npm target sharing a name with a bin key is left alone.
    facts["entry_points"] -= {c for c in facts["commands"] if "/" in c}

    return {
        "entry_points": sorted(facts["entry_points"]),
        "routes": sorted(facts["routes"]),
        "fsm_candidates": {k: sorted(v) for k, v in sorted(facts["fsm_candidates"].items())},
        "contracts": sorted(facts["contracts"]),
        "packages": sorted(facts["packages"]),
        "db_tables": sorted(facts["db_tables"]),
        "commands": sorted(facts["commands"]),
        "config_files": sorted(facts["config_files"]),
        "unsupported": sorted(facts["unsupported"]),
        "orm_detected": facts["orm_detected"],
        "public_paths": sorted(facts["public_paths"]),
        "public_prefixes": sorted(facts["public_prefixes"]),
        "auth_tier_active": facts["auth_tier_active"],
        "modules": sorted(facts["modules"]),
    }
