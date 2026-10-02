"""P2 — output honesty (trial F4/F5): distinguish 'scanned empty' from 'detector n/a'."""
import os
import shutil
from lib.extract import scan_repo
from lib.archmap import render_architecture

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def test_commands_include_sh_and_scripts(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "deploy.sh").write_text("#!/bin/bash\necho deploy\n")
    (d / "scripts").mkdir()
    (d / "scripts" / "migrate.py").write_text("print('x')\n")
    cmds = set(scan_repo(str(d))["commands"])
    assert "deploy.sh" in cmds                 # F5: root *.sh
    assert "scripts/migrate.py" in cmds         # F5: scripts/*
    assert "test" in cmds                       # Makefile still detected


def test_orm_detected_renders_tables():
    facts = scan_repo(FIX)                       # sample_app db.py imports sqlalchemy
    assert facts["orm_detected"] is True
    assert {"orders", "customers"} <= set(facts["db_tables"])
    assert "Tables: customers, orders" in render_architecture(FIX)


def test_db_na_when_no_orm(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "db.py").unlink()               # remove the only sqlalchemy user
    assert scan_repo(str(d))["orm_detected"] is False
    md = render_architecture(str(d))
    assert "Tables: n/a" in md                   # honest, not "0"/"(none)" (F4)
    assert "db_tables=n/a" in md                 # counts line too


def test_empty_commands_shows_scoped_note(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "Makefile").unlink()
    assert "none detected — Makefile" in render_architecture(str(d))
