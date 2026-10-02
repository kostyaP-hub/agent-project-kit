"""End-to-end CLI integration: scaffold -> archmap -> lint (+ adoption modes).

Locks the wiring the hyphenated CLI scripts add on top of the unit-tested lib.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
FIX = os.path.join(HERE, "fixtures", "sample_app")


def _run(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script), *args],
        capture_output=True, text=True,
    )


def test_full_pipeline(tmp_path):
    dst = tmp_path / "svc"
    shutil.copytree(FIX, dst)
    d = str(dst)

    # scaffold writes the cross-CLI wrappers + rules
    assert _run("ctx-scaffold.py", d, "--project", "svc").returncode == 0
    assert (dst / "GEMINI.md").exists()
    assert (dst / "CLAUDE.md").read_text().strip() == "@AGENTS.md"
    assert (dst / "GEMINI.md").read_text().strip() == "@AGENTS.md"

    # archmap: stale before write, fresh after
    assert _run("ctx-archmap.py", d, "--check").returncode == 1
    assert _run("ctx-archmap.py", d, "--write").returncode == 0
    assert (dst / "ARCHITECTURE.md").exists()
    assert _run("ctx-archmap.py", d, "--check").returncode == 0

    # lint clean on a fully-scaffolded, freshly-mapped repo
    assert _run("ctx-lint.py", d).returncode == 0


def test_adoption_modes_on_rule_drift(tmp_path):
    dst = tmp_path / "svc"
    shutil.copytree(FIX, dst)
    d = str(dst)
    _run("ctx-scaffold.py", d, "--project", "svc")
    # drift a universal-locked rule
    g = dst / "rules" / "git.md"
    g.write_text(g.read_text() + "\n- a locally-invented rule\n")

    assert _run("ctx-lint.py", d, "--mode=warn").returncode == 0    # advisory
    assert _run("ctx-lint.py", d, "--mode=block").returncode == 1   # blocking
    assert _run("ctx-lint.py", d, "--mode=audit").returncode == 0   # survey
