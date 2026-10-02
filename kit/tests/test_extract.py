"""Layer A — deterministic fact extraction from a repo via stdlib `ast`.

These tests pin the `scan_repo(root) -> dict` contract against a fixture app.
The whole point of Layer A is that STRUCTURE comes from the fact of code (no LLM),
so given the same source the same facts come out every time.
"""
import os
import shutil
from lib.extract import scan_repo

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def test_entry_points():
    eps = set(scan_repo(FIX)["entry_points"])
    assert "app.main:cli" in eps                    # pyproject [project.scripts]
    assert any(e.endswith("main.py") for e in eps)  # module-level __main__


def test_routes():
    routes = set(scan_repo(FIX)["routes"])
    assert "GET /health" in routes
    assert "POST /orders" in routes


def test_fsm_candidates():
    fsm = scan_repo(FIX)["fsm_candidates"]
    assert "OrderStatus" in fsm
    assert set(fsm["OrderStatus"]) == {"NEW", "PAID", "SHIPPED"}


def test_contracts():
    assert "Order" in set(scan_repo(FIX)["contracts"])


def test_packages():
    pkgs = set(scan_repo(FIX)["packages"])
    assert "app" in pkgs
    assert "app.core" in pkgs


def test_commands():
    cmds = set(scan_repo(FIX)["commands"])
    assert {"test", "lint", "run"} <= cmds          # Makefile targets


def test_db_tables():
    assert {"orders", "customers"} <= set(scan_repo(FIX)["db_tables"])


def test_config_files_redacted(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / ".env.production").write_text("DATABASE_URL=postgres://u:p@h:5432/db\n")
    (dst / "secrets.json").write_text('{"api_key": "sk-EXAMPLE-fake-key-for-tests"}\n')
    cfg = set(scan_repo(str(dst))["config_files"])
    assert ".env.production" not in cfg              # sensitive → redacted out
    assert "secrets.json" not in cfg
    assert "pyproject.toml" in cfg                   # legit config kept


def test_test_files_excluded(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / "tests").mkdir()
    (dst / "tests" / "test_helpers.py").write_text(
        "from pydantic import BaseModel\nclass FakeThing(BaseModel):\n    x: int\n")
    (dst / "test_top.py").write_text(
        "from pydantic import BaseModel\nclass FakeTop(BaseModel):\n    y: int\n")
    facts = scan_repo(str(dst))
    assert "FakeThing" not in facts["contracts"]   # in tests/ dir → excluded
    assert "FakeTop" not in facts["contracts"]      # test_*.py → excluded
    assert "Order" in facts["contracts"]            # real product model kept
    assert "tests" not in facts["packages"]


def test_deterministic():
    # same source -> identical facts (no LLM, no ordering nondeterminism)
    a = scan_repo(FIX)
    b = scan_repo(FIX)
    assert sorted(a["routes"]) == sorted(b["routes"])
    assert sorted(a["packages"]) == sorted(b["packages"])
