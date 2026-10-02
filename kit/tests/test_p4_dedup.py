"""P4-2 — a script listed as an ops command is not also an "entry point".

Cut pilot finding: every scripts/*.py with a __main__ guard was surfaced twice —
21 identical lines in §4 Entry points and again in §8 Commands (42 lines of a
108-line map). Same file, two detectors. It belongs under Commands (ops surface);
§4 should answer "how does the product start", not list build tooling.

Only PATH-shaped commands dedupe, so a Makefile/npm target that happens to share
a name with a bin entry is left alone.
"""
import os
import shutil
from lib.extract import scan_repo
from lib.archmap import render_architecture

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def _with_script(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "scripts").mkdir()
    (d / "scripts" / "run.py").write_text(
        "def main():\n    print('go')\n\n\nif __name__ == '__main__':\n    main()\n")
    return d


def test_script_is_command_not_entry_point(tmp_path):
    facts = scan_repo(str(_with_script(tmp_path)))
    assert "scripts/run.py" in facts["commands"]        # ops surface — kept
    assert "scripts/run.py" not in facts["entry_points"]  # not repeated as an entry point


def test_real_entry_points_survive(tmp_path):
    facts = scan_repo(str(_with_script(tmp_path)))
    assert any(e.endswith("app/main.py") for e in facts["entry_points"])  # product __main__
    assert "app.main:cli" in facts["entry_points"]                        # pyproject script


def test_render_lists_script_once(tmp_path):
    md = render_architecture(str(_with_script(tmp_path)))
    assert md.count("- scripts/run.py") == 1            # was 2 (§4 and §8)


def test_package_dunder_main_is_an_entry_point(tmp_path):
    """Gap the dedup exposed: a package __main__.py IS the way in (python -m pkg)
    but often has no `if __name__ == "__main__"` guard — Cut's raises SystemExit at
    module level. With the 21 scripts gone from §4, the map claimed "(none
    detected)" while a real entry point sat right there. Emit the PATH, not a
    dotted `python -m src.example_cut`: under src-layout the dotted form from the
    repo root is not the importable name, and a confidently wrong invocation is
    worse than a locatable file (same reasoning as the router-prefix refusal).
    """
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "__main__.py").write_text(
        "import sys\n\nfrom .main import cli\n\nraise SystemExit(cli())\n")
    eps = set(scan_repo(str(d))["entry_points"])
    assert "app/__main__.py" in eps            # no guard, still the entry point


def test_dunder_main_outside_package_ignored(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "loose").mkdir()
    (d / "loose" / "__main__.py").write_text("print('x')\n")   # no __init__.py
    assert "loose/__main__.py" not in set(scan_repo(str(d))["entry_points"])


def test_named_command_not_stripped(tmp_path):
    # only path-shaped commands dedupe: a bin key sharing a name with an npm
    # script is a different fact, not a duplicate listing.
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "package.json").write_text(
        '{"bin": {"tool": "./cli.js"}, "scripts": {"tool": "node cli.js"}}\n')
    facts = scan_repo(str(d))
    assert "tool" in facts["commands"]
    assert "tool" in facts["entry_points"]              # untouched by the dedup
