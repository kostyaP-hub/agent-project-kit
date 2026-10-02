"""P4-1 — module sub-grouping for module-monoliths (Cut pilot finding).

F7 grouped a route-monolith by path prefix. The analog for a MODULE-monolith
(Cut: 53 modules in one package, only 3 __init__.py) is grouping modules by
their package. The old §2 showed 3 package names — 53 modules invisible.

Unlike F7 (routes were already a counted fact, grouping is render-only), modules
were never extracted, so a module map not guarded by the drift gate would go
stale silently — exactly the bug the tool fights. So `modules` IS signature
material: adding/removing a module under a package moves signature_hash.
"""
import os
import shutil
from lib.extract import scan_repo
from lib.archmap import _module_section, render_architecture, build_anchors

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def test_modules_extracted_dotted():
    mods = set(scan_repo(FIX)["modules"])
    assert {"app.main", "app.db", "app.models", "app.core.config"} <= mods


def test_modules_exclude_tests_and_init(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "tests").mkdir()
    (d / "tests" / "test_x.py").write_text("x = 1\n")
    mods = set(scan_repo(str(d))["modules"])
    assert not any(m.endswith("__init__") for m in mods)   # package markers, not modules
    assert not any("test" in m for m in mods)              # test scaffolding excluded


def test_modules_exclude_loose_scripts(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "scripts").mkdir()
    (d / "scripts" / "build.py").write_text("if __name__ == '__main__':\n    pass\n")
    mods = set(scan_repo(str(d))["modules"])
    assert "scripts.build" not in mods         # no __init__.py → not a package tier
    assert "app.main" in mods                   # real package module still there


def test_module_section_groups_by_package():
    section = _module_section(["app", "app.core"],
                              ["app.main", "app.db", "app.models", "app.core.config"])
    assert "`app` (3):" in section
    assert "- main" in section and "- db" in section and "- models" in section
    assert "`app.core` (1):" in section
    assert "- config" in section


def test_render_shows_module_groups():
    md = render_architecture(FIX)
    assert "`app` (" in md                      # package header with count
    assert "- models" in md                     # module listed under its package


def test_modules_are_signature_material(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    before = build_anchors(scan_repo(str(d)))["signature_hash"]
    (d / "app" / "newmod.py").write_text("VALUE = 1\n")   # new module under a package
    after = build_anchors(scan_repo(str(d)))["signature_hash"]
    assert before != after                      # drift gate now guards the module map
