"""write_map — produce the map + wire it into AGENTS.md (no sidecar lock, F6)."""
import os
import shutil
from lib.archmap import write_map
from lib.lint import check_archmap

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def test_write_map_creates_map_and_hookup(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / "AGENTS.md").write_text("# app\n\n@./rules/git.md\n")
    res = write_map(str(dst))
    assert os.path.exists(res["map"])
    assert "@./ARCHITECTURE.md" in (dst / "AGENTS.md").read_text()
    assert res["hooked"] == "added"
    assert not (dst / ".ctx").exists()               # no sidecar lock (F6)
    assert check_archmap(str(dst))["status"] == "ok"  # what we wrote is fresh


def test_hookup_is_idempotent(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / "AGENTS.md").write_text("# app\n@./rules/git.md\n")
    write_map(str(dst))
    write_map(str(dst))
    assert (dst / "AGENTS.md").read_text().count("@./ARCHITECTURE.md") == 1


def test_write_without_agents_still_works(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    res = write_map(str(dst))
    assert os.path.exists(res["map"])
    assert res["hooked"] == "no_agents"


def test_second_write_reports_already_hooked(tmp_path):
    """"already wired" must not read as "you have no AGENTS.md" — one falsy value
    for both had the CLI tell people to scaffold a file they already had."""
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / "AGENTS.md").write_text("# Agents\n")
    assert write_map(str(dst))["hooked"] == "added"
    assert write_map(str(dst))["hooked"] == "already"
