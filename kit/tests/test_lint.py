"""archmap-freshness lint — the deterministic drift gate (spec v2 §X1/Verify).

Re-derives the structural signature from code and compares it to the one embedded
in ARCHITECTURE.md. This is the check the OLD ctx-lint FALSELY claimed to do.
Crucially: a formatting/comment change must NOT flag drift; a new route MUST.
"""
import os
import shutil
from lib.archmap import render_architecture, write_map
from lib.lint import check_archmap

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def _seed(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / "ARCHITECTURE.md").write_text(render_architecture(str(dst)))
    return dst


def test_fresh_map_ok(tmp_path):
    dst = _seed(tmp_path)
    assert check_archmap(str(dst))["status"] == "ok"


def test_missing_map(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    assert check_archmap(str(dst))["status"] == "missing"


def test_new_route_makes_map_stale(tmp_path):
    dst = _seed(tmp_path)
    (dst / "app" / "extra.py").write_text(
        "from fastapi import APIRouter\n"
        "r = APIRouter()\n\n"
        '@r.delete("/orders/{id}")\n'
        "def drop(id):\n"
        "    return id\n"
    )
    res = check_archmap(str(dst))
    assert res["status"] == "stale"
    assert res["expected"] != res["found"]
    assert "routes" in res["changed"]          # names exactly what moved


def test_formatting_change_stays_fresh(tmp_path):
    dst = _seed(tmp_path)
    p = dst / "app" / "main.py"
    p.write_text(p.read_text() + "\n\n# a trailing comment, no structural change\n")
    assert check_archmap(str(dst))["status"] == "ok"


def test_stale_report_names_only_what_moved(tmp_path):
    """Regression: the gate used to list fields that never changed.

    The header spelled `fsm=` / `db_tables=n/a` while the gate compared
    `fsm_candidates` / an int, so every stale report carried phantom
    `[None, 0]` entries — noise in the exact text a human reads to decide
    whether the drift matters.
    """
    dst = _seed(tmp_path)
    p = dst / "app" / "main.py"  # existing module: only the route count may move
    p.write_text(p.read_text() + '\n\n@app.get("/only-a-route")\ndef only_a_route():\n    return {}\n')
    changed = check_archmap(str(dst))["changed"]
    assert set(changed) == {"routes"}, f"phantom drift reported: {changed}"


def test_map_can_live_outside_repo_root(tmp_path):
    """A repo that already owns a hand-written docs/ARCHITECTURE.md needs the
    generated map somewhere unambiguous — write and check must agree on it."""
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    rel = "docs/ARCHITECTURE.auto.md"
    write_map(str(dst), map_path=rel)
    assert (dst / rel).exists()
    assert check_archmap(str(dst), rel)["status"] == "ok"
    # the default location stays empty — no surprise second map at the root
    assert not (dst / "ARCHITECTURE.md").exists()
    assert check_archmap(str(dst))["status"] == "missing"


def test_written_map_carries_no_branch_name(tmp_path):
    """A committed map must not bake in the branch it was generated on: after a
    squash-merge that line is simply false, and it is churn on the one line every
    concurrent PR touches. Provenance stays on the stdout preview only."""
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    write_map(str(dst))
    written = (dst / "ARCHITECTURE.md").read_text()
    assert "Source:" not in written and "source:" not in written
    assert "Source:" in render_architecture(str(dst))  # preview still says where it came from
