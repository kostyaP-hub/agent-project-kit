"""Completeness items (spec v2 §Q1/Q2, Codex-flagged gaps):
.ctxignore support (ignore strategy) + load_strategy frontmatter validation.
"""
import os
import shutil
from lib.extract import scan_repo
from lib.lint import check_load_strategy

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


# ---- .ctxignore ----

def test_ctxignore_prunes_dir(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / ".ctxignore").write_text("app/core/\n")
    facts = scan_repo(str(dst))
    assert "app.core" not in facts["packages"]      # ignored subtree gone
    assert "app" in facts["packages"]               # rest intact


def test_ctxignore_skips_config_file(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / "extra.toml").write_text("[x]\n")
    (dst / ".ctxignore").write_text("extra.toml\n")
    cfg = set(scan_repo(str(dst))["config_files"])
    assert "extra.toml" not in cfg
    assert "pyproject.toml" in cfg


def test_no_ctxignore_is_fine(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    assert "app.core" in scan_repo(str(dst))["packages"]


# ---- load_strategy ----

def _agents(dst, strategy=None):
    fm = f"---\nproject: \"x\"\n{('load_strategy: ' + strategy) if strategy else ''}\n---\n# x\n"
    (dst / "AGENTS.md").write_text(fm)


def test_valid_load_strategy_ok(tmp_path):
    _agents(tmp_path, "alpha")
    assert check_load_strategy(str(tmp_path)) is None


def test_invalid_load_strategy_flagged(tmp_path):
    _agents(tmp_path, "bogus")
    assert check_load_strategy(str(tmp_path)) == "bogus"


def test_absent_load_strategy_ok(tmp_path):
    _agents(tmp_path, None)
    assert check_load_strategy(str(tmp_path)) is None
