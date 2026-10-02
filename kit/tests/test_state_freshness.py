import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRESHNESS = ROOT / "lib" / "state_freshness.py"
spec = importlib.util.spec_from_file_location("state_freshness", FRESHNESS)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True)

def state(anchor=None):
    return """schema_version: 1
project: example-project
status: live
updated: 2026-09-08
""" + (f'head_sha: "{anchor}"\n' if anchor else "") + """pointers:
  vault_entity: docs/entity.md
next_action: Keep it current.
"""

def repo(tmp_path):
    root = tmp_path / "repo"; root.mkdir(parents=True); git(root, "init"); git(root, "config", "user.name", "Test"); git(root, "config", "user.email", "test@example.com")
    (root / "code.txt").write_text("one\n"); git(root, "add", "code.txt"); git(root, "commit", "-m", "initial")
    return root

def clone_with_origin(tmp_path, branch="main"):
    origin = tmp_path / "origin.git"; git(tmp_path, "init", "--bare", str(origin))
    root = tmp_path / "seed"; git(tmp_path, "clone", str(origin), str(root))
    git(root, "config", "user.name", "Test"); git(root, "config", "user.email", "test@example.com")
    git(root, "checkout", "-b", branch)
    (root / "code.txt").write_text("one\n"); git(root, "add", "code.txt"); git(root, "commit", "-m", "initial")
    anchor = git(root, "rev-parse", "HEAD").stdout.strip()[:12]
    (root / "project.state").write_text(state(anchor)); git(root, "add", "project.state"); git(root, "commit", "-m", "state")
    git(root, "push", "-u", "origin", branch)
    git(origin, "symbolic-ref", "HEAD", "refs/heads/" + branch)
    git(root, "remote", "set-head", "origin", "-a")
    return root, origin

def test_no_state_and_no_anchor(tmp_path):
    root = repo(tmp_path)
    assert module.check(root)["status"] == "no_state"
    (root / "project.state").write_text(state())
    assert module.check(root)["status"] == "no_anchor"

def test_fresh_stale_and_state_only_commit(tmp_path):
    root = repo(tmp_path); anchor = git(root, "rev-parse", "HEAD").stdout.strip()[:12]
    (root / "project.state").write_text(state(anchor)); git(root, "add", "project.state"); git(root, "commit", "-m", "state")
    assert module.check(root)["status"] == "fresh"
    (root / "code.txt").write_text("two\n"); git(root, "commit", "-am", "code")
    got = module.check(root); assert got["status"] == "stale" and got["code_commits_after"] == 1
    # A new anchor stamped before the state-only commit remains fresh.
    current = git(root, "rev-parse", "HEAD").stdout.strip()[:12]
    (root / "project.state").write_text(state(current)); git(root, "add", "project.state"); git(root, "commit", "-m", "restamp")
    assert module.check(root)["status"] == "fresh"

def test_anchor_unreachable_and_worktree(tmp_path):
    root = repo(tmp_path); old = git(root, "rev-parse", "HEAD").stdout.strip()[:12]
    (root / "project.state").write_text(state(old)); git(root, "add", "project.state"); git(root, "commit", "-m", "state")
    git(root, "checkout", "--orphan", "rewritten"); git(root, "add", "-A"); git(root, "commit", "-m", "rewritten history")
    assert module.check(root)["status"] == "anchor_unreachable"
    anchor = git(root, "rev-parse", "HEAD").stdout.strip()[:12]
    (root / "project.state").write_text(state(anchor)); git(root, "add", "project.state"); git(root, "commit", "-m", "state again")
    wt = tmp_path / "worktree"; git(root, "worktree", "add", "-b", "wt", str(wt))
    assert module.check(wt)["status"] == "fresh"

def test_origin_mainline_feature_and_detached_branch_awareness(tmp_path):
    root, _ = clone_with_origin(tmp_path)
    assert module.check(root)["status"] == "fresh"
    (root / "code.txt").write_text("two\n"); git(root, "commit", "-am", "code")
    assert module.check(root)["status"] == "stale"
    git(root, "checkout", "-b", "feature")
    result = module.check(root)
    assert result["status"] == "feature_branch" and result["state_touched"] is False
    (root / "project.state").write_text(state(git(root, "rev-parse", "HEAD").stdout.strip()[:12]))
    git(root, "add", "project.state"); git(root, "commit", "-m", "bad state stamp")
    assert module.check(root)["state_touched"] is True
    git(root, "checkout", "--detach")
    detached = module.check(root)
    assert detached["status"] == "feature_branch" and "Ветка detached" in detached["detail"]

def test_missing_origin_head_accepts_master(tmp_path):
    root, _ = clone_with_origin(tmp_path, "master")
    git(root, "update-ref", "-d", "refs/remotes/origin/HEAD")
    assert module.check(root)["status"] == "fresh"
