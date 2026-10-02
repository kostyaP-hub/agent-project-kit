"""universal content-hash lock (spec v2 §Q1/X1).

git/secrets/worktree/commits/auth-payments must be byte-identical to the single
source everywhere (this is the drift the OLD ctx-lint claimed to catch and didn't).
stack/testing/boundaries/focus are per-project and are NOT checked.
Normalization: trailing-whitespace / blank-line noise must NOT count as drift.
"""
import os
import shutil
from lib.lint import check_rules_drift, UNIVERSAL_RULES

SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rules")


def _repo_with_rules(tmp_path, names):
    rules = tmp_path / "repo" / "rules"
    rules.mkdir(parents=True)
    for fn in names:
        shutil.copy(os.path.join(SRC, fn), rules / fn)
    return tmp_path / "repo"


def test_identical_copies_no_drift(tmp_path):
    repo = _repo_with_rules(tmp_path, UNIVERSAL_RULES)
    assert check_rules_drift(str(repo), SRC) == []


def test_whitespace_only_change_is_not_drift(tmp_path):
    repo = _repo_with_rules(tmp_path, UNIVERSAL_RULES)
    p = repo / "rules" / "git.md"
    p.write_text(p.read_text() + "   \n\n\n")          # trailing spaces + blank lines
    assert check_rules_drift(str(repo), SRC) == []


def test_content_change_flags_drift(tmp_path):
    repo = _repo_with_rules(tmp_path, UNIVERSAL_RULES)
    p = repo / "rules" / "git.md"
    p.write_text(p.read_text() + "\n- a locally-invented rule\n")
    assert ("git.md", "drift") in check_rules_drift(str(repo), SRC)


def test_missing_universal_flagged(tmp_path):
    repo = _repo_with_rules(tmp_path, [n for n in UNIVERSAL_RULES if n != "git.md"])
    assert ("git.md", "missing") in check_rules_drift(str(repo), SRC)


def test_per_project_rule_not_checked(tmp_path):
    repo = _repo_with_rules(tmp_path, UNIVERSAL_RULES)
    (repo / "rules" / "stack.md").write_text("# totally custom stack\n")
    flagged = {fn for fn, _ in check_rules_drift(str(repo), SRC)}
    assert "stack.md" not in flagged                    # customizable, exempt
