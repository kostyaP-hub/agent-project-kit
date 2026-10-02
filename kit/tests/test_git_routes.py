"""F1 (git-tracked inventory) + F2 (router prefix honesty) — trial findings."""
import os
import shutil
import subprocess
from lib.extract import scan_repo

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def _git_init(d):
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], cwd=d, check=True)


def test_untracked_files_excluded_via_git(tmp_path):
    d = tmp_path / "repo"
    shutil.copytree(FIX, d)
    _git_init(str(d))
    (d / "scratch_untracked.py").write_text(
        'from fastapi import FastAPI\napp = FastAPI()\n\n@app.get("/leak")\ndef f():\n    return 1\n')
    routes = set(scan_repo(str(d))["routes"])
    assert "GET /leak" not in routes      # untracked scratch → not in the map (F1)
    assert "GET /health" in routes        # tracked → present


def test_router_prefix_marks_unsupported(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "pref.py").write_text(
        'from fastapi import APIRouter\nr = APIRouter(prefix="/api/v2")\n\n'
        '@r.get("/items")\ndef f():\n    return 1\n')
    facts = scan_repo(str(d))             # tmp not a git repo → os.walk fallback
    assert "GET /items" not in facts["routes"]                 # no confident wrong path (F2)
    assert any("pref.py" in u for u in facts["unsupported"])   # honest refusal recorded
    assert "GET /health" in facts["routes"]                    # unprefixed module still fine


def test_map_has_git_provenance(tmp_path):
    from lib.archmap import render_architecture
    d = tmp_path / "repo"
    shutil.copytree(FIX, d)
    _git_init(str(d))
    md = render_architecture(str(d))
    assert "> Source:" in md and "@ " in md           # branch @ sha7 (F3)
    (d / "app" / "new.py").write_text("x = 1\n")       # uncommitted change
    assert "dirty" in render_architecture(str(d))      # dirty flag surfaces
