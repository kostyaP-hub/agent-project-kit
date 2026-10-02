"""P4-4 — additive scaffold for repos that already have a hand-written AGENTS.md.

Cut pilot finding: scaffold was a dead end in both directions on such a repo —
without --force it STOPs (so rules/ + GEMINI.md never land), with --force it
clobbers a hand-written AGENTS.md (Cut's 22 lines of hard rules: immutable
reference timeline, marker customData, read-back verify). --additive keeps the
existing file and appends the rules imports, like archmap's @-hookup does.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
FIX = os.path.join(HERE, "fixtures", "sample_app")

HAND_WRITTEN = """# AGENTS.md — legacy service

Navigation doc. **Source of truth = the vault entity**, not this file.

## Hard rules
1. Reference timeline is immutable. Never mutate the reference.
2. Stable clip identity via marker customData — NEVER address clips by index.
3. Read-back verify after every apply.
"""


def _run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          capture_output=True, text=True)


def _repo_with_agents(tmp_path):
    d = tmp_path / "svc"
    shutil.copytree(FIX, d)
    (d / "AGENTS.md").write_text(HAND_WRITTEN)
    return d


def test_additive_preserves_existing_content(tmp_path):
    d = _repo_with_agents(tmp_path)
    assert _run("ctx-scaffold.py", str(d), "--additive").returncode == 0
    txt = (d / "AGENTS.md").read_text()
    for line in HAND_WRITTEN.strip().splitlines():
        assert line in txt                       # not one hand-written line lost


def test_additive_appends_rule_imports(tmp_path):
    d = _repo_with_agents(tmp_path)
    _run("ctx-scaffold.py", str(d), "--additive")
    txt = (d / "AGENTS.md").read_text()
    assert "@./rules/git.md" in txt              # rules now actually load for every CLI
    assert "@./rules/secrets.md" in txt


def test_additive_is_idempotent(tmp_path):
    d = _repo_with_agents(tmp_path)
    _run("ctx-scaffold.py", str(d), "--additive")
    once = (d / "AGENTS.md").read_text()
    _run("ctx-scaffold.py", str(d), "--additive")
    twice = (d / "AGENTS.md").read_text()
    assert once == twice                         # second run is a no-op
    assert twice.count("@./rules/git.md") == 1   # no duplicated section


def test_additive_lands_rules_and_wrappers(tmp_path):
    d = _repo_with_agents(tmp_path)
    _run("ctx-scaffold.py", str(d), "--additive")
    assert (d / "rules" / "git.md").exists()     # what the STOP used to block
    assert (d / "GEMINI.md").read_text().strip() == "@AGENTS.md"
    assert (d / "CLAUDE.md").read_text().strip() == "@AGENTS.md"


def test_scaffold_lands_justfile_and_adr_templates(tmp_path):
    d = _repo_with_agents(tmp_path)
    assert _run("ctx-scaffold.py", str(d), "--additive").returncode == 0
    assert "check = полный локальный DoD" in (d / "justfile").read_text()
    assert (d / "docs" / "decisions" / "README.md").exists()
    assert (d / "docs" / "decisions" / "0000-template.md").exists()


def test_no_justfile_skips_justfile_and_adr_templates(tmp_path):
    d = _repo_with_agents(tmp_path)
    assert _run("ctx-scaffold.py", str(d), "--additive", "--no-justfile").returncode == 0
    assert not (d / "justfile").exists()
    assert (d / "docs" / "decisions" / "README.md").exists()
    assert (d / "docs" / "decisions" / "0000-template.md").exists()


def test_plain_run_still_stops_but_points_at_additive(tmp_path):
    d = _repo_with_agents(tmp_path)
    r = _run("ctx-scaffold.py", str(d))
    assert r.returncode == 1                     # unchanged: no silent surprise
    assert "--additive" in r.stdout              # but no longer a dead end
    assert (d / "AGENTS.md").read_text() == HAND_WRITTEN   # untouched


def test_additive_then_lint_is_clean(tmp_path):
    # e2e: the whole point — a repo with its own AGENTS.md becomes compliant.
    # Assert zero WARNINGS too: exit 0 alone would pass even before the fix,
    # since the missing-GEMINI/rules findings are advisory in the default mode.
    d = _repo_with_agents(tmp_path)
    _run("ctx-scaffold.py", str(d), "--additive")
    r = _run("ctx-lint.py", str(d))
    assert r.returncode == 0
    assert "0 errors, 0 warnings" in r.stdout
    assert _run("ctx-lint.py", str(d), "--mode=block").returncode == 0  # survives strict mode
