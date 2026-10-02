import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ctx-lint.py"
SPEC = importlib.util.spec_from_file_location("ctx_lint_cli", SCRIPT)
ctx_lint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ctx_lint)


def _repo(tmp_path, text):
    path = tmp_path / "repo"
    path.mkdir()
    (path / "AGENTS.md").write_text(text, encoding="utf-8")
    return path


def test_git_add_all_is_error(tmp_path):
    issues, exceptions = ctx_lint.forbidden_issues(str(_repo(tmp_path, "Use `git add -A`.\n")))
    assert exceptions == []
    assert [(issue["id"], issue["severity"]) for issue in issues] == [("git-add-all", "error")]


def test_push_after_explicit_approval_is_allowed(tmp_path):
    issues, _ = ctx_lint.forbidden_issues(str(_repo(tmp_path, "после явного approval: git push origin main\n")))
    assert not [issue for issue in issues if issue["id"] == "push-without-gate"]


def test_documented_exception_is_not_a_violation(tmp_path):
    repo = _repo(tmp_path, "Exception: legacy release script нельзя переписать сейчас\ngit add -A\n")
    issues, exceptions = ctx_lint.forbidden_issues(str(repo))
    assert not issues
    assert exceptions and exceptions[0]["id"] == "git-add-all"


def test_clean_file_has_no_forbidden_lines(tmp_path):
    issues, exceptions = ctx_lint.forbidden_issues(str(_repo(tmp_path, "Run focused tests, then report results.\n")))
    assert issues == []
    assert exceptions == []
