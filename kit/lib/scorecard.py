"""Fleet-level repository scorecard for ctx-lint.

All git probes are deliberately bounded: a stale mount or broken worktree must
turn into a visible ``?``, never hang the fleet report.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from lib.config import load_config
from lib.lint import check_archmap, check_rules_drift

FIELDS = ("repo", "kind", "entity", "vault_status", "agents", "claude", "rules",
          "legibility", "project_state", "ci", "worktrees", "dirty", "ahead", "last_commit")
_STATUS_RE = re.compile(r"^status:\s*(.*?)\s*$", re.MULTILINE)


def _git(repo, *args):
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], text=True,
                                capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None, True
    return result, False


def _git_value(repo, *args):
    result, failed = _git(repo, *args)
    if failed or result.returncode:
        return None
    return result.stdout.strip()


def _is_git(repo):
    """None means a git probe failed; False means an ordinary context folder."""
    if not os.path.exists(os.path.join(repo, ".git")):
        return False
    result, failed = _git(repo, "rev-parse", "--is-inside-work-tree")
    if failed:
        return None
    if result.returncode:
        return None
    return result.stdout.strip() == "true"


def _common_dir(repo):
    value = _git_value(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.realpath(value) if value else None


def dedupe_repos(repos):
    """Return one representative per common git dir, with extra-worktree count."""
    grouped, standalone = {}, []
    for raw in repos:
        repo = os.path.abspath(os.path.expanduser(str(raw)))
        state = _is_git(repo)
        if state is True:
            common = _common_dir(repo)
            if common:
                grouped.setdefault(common, []).append(repo)
            else:
                standalone.append((repo, "?"))
        else:
            standalone.append((repo, 0))
    out = standalone[:]
    for entries in grouped.values():
        entries.sort(key=lambda p: (not os.path.isdir(os.path.join(p, ".git")), p))
        # Считаем ВСЕ worktree репо по `git worktree list`, а не только найденные сканом:
        # брошенные worktree часто лежат вне scan-roots или в .worktrees/, и именно они — цель уборки.
        out.append((entries[0], _worktree_count(entries[0], fallback=len(entries) - 1)))
    return sorted(out, key=lambda item: item[0])


def _worktree_count(repo, fallback=0):
    """Число дополнительных worktree (включая prunable) по git worktree list --porcelain."""
    result, failed = _git(repo, "worktree", "list", "--porcelain")
    if failed or result.returncode:
        return fallback
    count = sum(1 for line in result.stdout.splitlines() if line.startswith("worktree "))
    return max(count - 1, 0)


def _origin_kind(repo, owned):
    result, failed = _git(repo, "remote", "get-url", "origin")
    if failed:
        return "?"
    if result.returncode:
        return "no-remote"
    url = result.stdout.strip()
    if not url:
        return "no-remote"
    namespace = re.search(r"[/:]([^/]+)/[^/]+?(?:\.git)?$", url)
    if not namespace:
        return "upstream"
    return "owned" if any(namespace.group(1).lower().startswith(x.lower()) for x in owned) else "upstream"


def _entity_regex(entity_glob):
    """Turn the configured relative card glob into a link-matching regex."""
    pattern = entity_glob.replace("\\", "/").lstrip("./")
    marker = r"([A-Za-z0-9][A-Za-z0-9_-]*)"
    escaped = re.escape(pattern)
    star = escaped.rfind(r"\*")
    if star < 0:
        return None
    escaped = escaped[:star] + marker + escaped[star + 2:]
    escaped = escaped.replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    return re.compile(escaped)


def _card_path(knowledge_root, entity_glob, entity):
    pattern = entity_glob.replace("\\", "/").lstrip("./")
    if "*" not in pattern:
        return None
    return Path(knowledge_root) / pattern.replace("*", entity, 1)


def _entity_and_status(repo, knowledge_root, entity_glob):
    if knowledge_root is None or not isinstance(entity_glob, str):
        return "—", "—"
    entity_re = _entity_regex(entity_glob)
    if entity_re is None:
        return "—", "—"
    entity = None
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = os.path.join(repo, name)
        if os.path.isfile(path):
            match = entity_re.search(Path(path).read_text(encoding="utf-8"))
            if match:
                entity = match.group(1)
                break
    if not entity:
        return "—", "—"
    card = _card_path(knowledge_root, entity_glob, entity)
    if card is None:
        return entity, "—"
    try:
        card_text = card.read_text(encoding="utf-8")
        frontmatter = card_text.split("\n---", 1)[0] if card_text.startswith("---\n") else ""
        match = _STATUS_RE.search(frontmatter)
    except OSError:
        match = None
    return entity, match.group(1).strip().strip("\"'") if match else "—"


def _claude(repo):
    path = Path(repo) / "CLAUDE.md"
    if not path.is_file():
        return "none"
    agents = Path(repo) / "AGENTS.md"
    try:
        if agents.is_file() and path.samefile(agents):
            return "wrapper"
    except OSError:
        pass
    lines = path.read_text(encoding="utf-8").splitlines()
    return "wrapper" if len(lines) <= 10 and any(line.strip() in {"@AGENTS.md", "@./AGENTS.md"} for line in lines) else "full"


def _project_state(repo):
    if not any((Path(repo) / name).is_file() for name in ("project.state", "project.state.yaml", "project.state.yml")):
        return "✗"
    validator = Path(__file__).resolve().parents[1] / "scripts" / "project-state-validate.py"
    try:
        result = subprocess.run([sys.executable, str(validator), "--repo", str(repo)],
                                text=True, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return "invalid"
    return "✓" if result.returncode == 0 else "invalid"


def scorecard_row(repo, owned, worktrees=0, knowledge_root=None, knowledge_entity_glob=None):
    root = os.path.abspath(os.path.expanduser(str(repo)))
    config = load_config()
    knowledge_root = config["knowledge_root"] if knowledge_root is None else knowledge_root
    knowledge_entity_glob = (config["knowledge_entity_glob"] if knowledge_entity_glob is None
                             else knowledge_entity_glob)
    git_state = _is_git(root)
    entity, vault_status = _entity_and_status(root, knowledge_root, knowledge_entity_glob)
    row = {
        "repo": os.path.basename(os.path.normpath(root)), "kind": "no-git", "entity": entity,
        "vault_status": vault_status, "agents": "✓" if (Path(root) / "AGENTS.md").exists() else "✗",
        "claude": _claude(root),
        "rules": "✓" if (Path(root) / "rules").is_dir() and not check_rules_drift(root) else "✗",
        "legibility": "✓" if check_archmap(root)["status"] == "ok" else "✗",
        "project_state": _project_state(root),
        "ci": "✓" if list((Path(root) / ".github" / "workflows").glob("*.yml")) else "✗",
        "worktrees": worktrees, "dirty": "—", "ahead": "—", "last_commit": "—", "path": root,
    }
    if git_state is False:
        return row
    if git_state is None:
        row.update(kind="?", dirty="?", ahead="?", last_commit="?")
        return row
    row["kind"] = _origin_kind(root, owned)
    status = _git_value(root, "status", "--porcelain")
    row["dirty"] = "?" if status is None else len(status.splitlines())
    upstream = _git_value(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream is None:
        row["ahead"] = "—"
    else:
        ahead = _git_value(root, "rev-list", "--count", "@{u}..HEAD")
        row["ahead"] = "?" if ahead is None else int(ahead)
    commit = _git_value(root, "log", "-1", "--format=%cs")
    row["last_commit"] = "?" if commit is None else commit
    return row


def build_scorecard(repos, owned, knowledge_root=None, knowledge_entity_glob=None):
    return [scorecard_row(repo, owned, worktrees, knowledge_root, knowledge_entity_glob)
            for repo, worktrees in dedupe_repos(repos)]


def render_scorecard(rows):
    lines = ["| " + " | ".join(FIELDS) + " |", "|" + "---|" * len(FIELDS)]
    for row in rows:
        lines.append("| " + " | ".join(str(row[field]) for field in FIELDS) + " |")
    return "\n".join(lines)


def summary(rows):
    kinds = {kind: sum(row["kind"] == kind for row in rows) for kind in ("owned", "upstream", "no-remote", "no-git")}
    grade_a = sum(row["agents"] == "✓" and row["claude"] == "wrapper" and row["rules"] == "✓" and row["project_state"] == "✓" for row in rows)
    numeric = lambda field: sum(row[field] for row in rows if isinstance(row[field], int))
    return (f"Всего репо: {len(rows)}; owned: {kinds['owned']}; upstream: {kinds['upstream']}; "
            f"no-remote: {kinds['no-remote']}; no-git: {kinds['no-git']}; full tier A: {grade_a}; "
            f"full CLAUDE.md: {sum(row['claude'] == 'full' for row in rows)}; worktrees: {numeric('worktrees')}; "
            f"dirty: {sum(isinstance(row['dirty'], int) and row['dirty'] > 0 for row in rows)}; ahead: {sum(isinstance(row['ahead'], int) and row['ahead'] > 0 for row in rows)}")


def generated_markdown(rows):
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return f"%% AUTO-GENERATED by ctx-lint --scorecard · built {timestamp} · do not edit %%\n\n{summary(rows)}\n\n{render_scorecard(rows)}\n"
