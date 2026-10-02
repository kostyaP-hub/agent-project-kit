"""Git-backed freshness check for the small project.state contract."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

STATE_NAMES = ("project.state", "project.state.yaml", "project.state.yml")
_VALIDATOR = Path(__file__).resolve().parents[1] / "scripts" / "project-state-validate.py"

def _load_validator():
    spec = importlib.util.spec_from_file_location("project_state_validate", _VALIDATOR)
    if spec is None or spec.loader is None:
        raise ImportError("validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _git(repo: Path, args: list[str], timeout: int) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], text=True,
                              capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None

def default_branch_kind(root, timeout=10):
    """Return whether HEAD is the branch that owns project.state, and its label."""
    origin = _git(root, ["remote", "get-url", "origin"], timeout)
    branch = _git(root, ["symbolic-ref", "-q", "--short", "HEAD"], timeout)
    branch_name = branch.stdout.strip() if branch is not None and not branch.returncode else ""
    if origin is None or origin.returncode:
        return True, branch_name or "solo"
    if not branch_name:
        return False, "detached"
    remote_head = _git(root, ["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], timeout)
    if remote_head is not None and not remote_head.returncode and remote_head.stdout.strip():
        default = remote_head.stdout.strip()
        if default.startswith("origin/"):
            default = default[len("origin/"):]
        return branch_name == default, branch_name
    return branch_name in {"main", "master"}, branch_name

def _result(status: str, repo: Path, state_path: Path | None = None, head_sha=None,
            code_commits_after=None, latest_code_commit=None, detail="", state_touched=None) -> dict:
    return {"status": status, "repo": str(repo),
            "state_path": str(state_path) if state_path else None, "head_sha": head_sha,
            "code_commits_after": code_commits_after, "latest_code_commit": latest_code_commit,
            "detail": detail, "state_touched": state_touched}

def check(repo, timeout=10) -> dict:
    """Return a non-raising freshness verdict for *repo*."""
    requested = Path(repo).expanduser().resolve()
    top = _git(requested, ["rev-parse", "--show-toplevel"], timeout)
    if top is None or top.returncode:
        return _result("not_git", requested, detail="Каталог не является доступным Git-репозиторием.")
    root = Path(top.stdout.strip())
    state_path = next((root / n for n in STATE_NAMES if (root / n).is_file()), None)
    if state_path is None:
        return _result("no_state", root, detail="Файл project.state в корне репозитория не найден.")
    try:
        validator = _load_validator()
        data = validator.yaml_subset(state_path.read_text(encoding="utf-8"))
        errors = validator.validate(data)
    except (OSError, ValueError, ImportError) as exc:
        return _result("invalid_state", root, state_path, detail=f"project.state не читается: {exc}")
    if errors:
        return _result("invalid_state", root, state_path, detail="project.state не проходит проверку схемы.")
    is_mainline, branch_label = default_branch_kind(root, timeout)
    if not is_mainline:
        state_touched = False
        remote_head = _git(root, ["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], timeout)
        default_ref = remote_head.stdout.strip() if remote_head is not None and not remote_head.returncode else ""
        if not default_ref:  # клон без origin/HEAD: берём существующую origin/main|master
            for name in ("origin/main", "origin/master"):
                ref = _git(root, ["rev-parse", "--verify", "-q", "refs/remotes/" + name], timeout)
                if ref is not None and not ref.returncode:
                    default_ref = name
                    break
        if default_ref.startswith("origin/"):
            merge_base = _git(root, ["merge-base", "HEAD", default_ref], timeout)
            if merge_base is not None and not merge_base.returncode and merge_base.stdout.strip():
                diff = _git(root, ["diff", "--quiet", merge_base.stdout.strip(), "HEAD", "--", *STATE_NAMES], timeout)
                if diff is not None:
                    state_touched = diff.returncode == 1
        return _result(
            "feature_branch", root, state_path,
            detail=(f"Ветка {branch_label}: project.state описывает default-ветку и штампуется после мержа "
                    "(единственным release-процессом); «дальше» ветки — в PR, раздел «## Дальше»."),
            state_touched=state_touched,
        )
    anchor = data.get("head_sha")
    if not anchor:
        return _result("no_anchor", root, state_path, detail="В project.state нет якоря head_sha.")
    exists = _git(root, ["cat-file", "-e", f"{anchor}^{{commit}}"], timeout)
    ancestor = _git(root, ["merge-base", "--is-ancestor", anchor, "HEAD"], timeout)
    if exists is None or ancestor is None or exists.returncode or ancestor.returncode:
        return _result("anchor_unreachable", root, state_path, anchor, detail="Якорь head_sha недостижим из текущего HEAD.")
    # Один проход git log вместо diff-tree на каждый коммит: после старого якоря коммитов могут быть сотни.
    log = _git(root, ["log", "--no-renames", "--name-only", "--format=%x00%H", f"{anchor}..HEAD"], timeout)
    if log is None or log.returncode:
        return _result("anchor_unreachable", root, state_path, anchor, detail="Не удалось проверить историю после head_sha.")
    code = []
    for block in log.stdout.split("\0")[1:]:
        lines = [line for line in block.splitlines() if line]
        if lines and any(path not in STATE_NAMES for path in lines[1:]):
            code.append(lines[0])
    if code:
        return _result("stale", root, state_path, anchor, len(code), code[0][:12],
                       f"После head_sha {anchor[:7]} коммитов с кодом: {len(code)}, последний {code[0][:7]}.")
    return _result("fresh", root, state_path, anchor, 0, None,
                   "После head_sha нет коммитов с изменениями кода.")
