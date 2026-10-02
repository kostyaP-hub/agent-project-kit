import subprocess
import sys
from pathlib import Path
from test_state_freshness import clone_with_origin, git, repo, state
from test_state_freshness import module as freshness

ROOT = Path(__file__).resolve().parents[1]
STAMP = ROOT / "scripts" / "project-state-stamp.py"
def run(repo, *args): return subprocess.run([sys.executable, str(STAMP), "--repo", str(repo), *args], text=True, capture_output=True)

def test_stamp_refuses_dirty_and_allow_dirty(tmp_path):
    root = repo(tmp_path); (root / "project.state").write_text(state()); (root / "code.txt").write_text("dirty\n")
    assert run(root).returncode == 2
    assert run(root, "--allow-dirty").returncode == 0
    assert freshness.check(root)["status"] == "fresh"

def test_stamp_inserts_preserves_and_rejects_long_value(tmp_path):
    root = repo(tmp_path); original = "# preserve me\n" + state()
    (root / "project.state").write_text(original)
    result = run(root, "--next-action", "A \\\\ B \"C\"")
    text = (root / "project.state").read_text()
    assert result.returncode == 0 and "# preserve me" in text and "head_sha:" in text and 'next_action: "A \\\\\\\\ B \\"C\\""' in text
    before = text; assert run(root, "--next-action", "x" * 201).returncode == 2
    assert (root / "project.state").read_text() == before

def test_stamp_restores_invalid_result(tmp_path):
    root = repo(tmp_path); original = state().replace("status: live", "status: invalid")
    (root / "project.state").write_text(original)
    result = run(root)
    assert result.returncode == 1 and (root / "project.state").read_text() == original

def test_stamp_allows_untracked_only_with_warning(tmp_path):
    root = repo(tmp_path); (root / "project.state").write_text(state()); (root / "scratch.log").write_text("junk\n")
    result = run(root)
    assert result.returncode == 0 and "неотслеживаемых файлов 1" in result.stderr

def test_stamp_refuses_feature_branch_unless_explicitly_allowed(tmp_path):
    root, _ = clone_with_origin(tmp_path); git(root, "checkout", "-b", "feature")
    before = (root / "project.state").read_text()
    refused = run(root)
    assert refused.returncode == 2 and "только на default-ветке" in refused.stderr
    assert (root / "project.state").read_text() == before
    assert run(root, "--allow-branch").returncode == 0

def test_stamp_works_on_origin_main(tmp_path):
    root, _ = clone_with_origin(tmp_path)
    assert run(root, "--next-action", "После мержа проверить выпуск.").returncode == 0
