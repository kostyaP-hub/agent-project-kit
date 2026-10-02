"""P3 / F9 — module-level MANIFEST dict literals are plugin contracts.

Trial finding: contracts caught only BaseModel/TypedDict/@dataclass, but the
portal's real contract surface is `MANIFEST = {name, path, icon, required_role,
enabled}` per module — a literal module-level dict, AST-extractable, and exactly
the answer to "how do I add a section". Scope: MANIFEST / *_MANIFEST dicts only
(other repo-specific registry names would need opt-in like F8).
"""
import os
import shutil
from lib.extract import scan_repo

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def test_manifest_dict_is_contract(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "plugin.py").write_text(
        'MANIFEST = {\n'
        '    "name": "funnel",\n    "path": "/modules/funnel",\n'
        '    "icon": "chart",\n    "required_role": "admin",\n    "enabled": True,\n}\n')
    assert "MANIFEST" in set(scan_repo(str(d))["contracts"])


def test_suffixed_manifest_is_contract(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "reg.py").write_text('FUNNEL_MANIFEST = {"name": "x", "path": "/y"}\n')
    assert "FUNNEL_MANIFEST" in set(scan_repo(str(d))["contracts"])


def test_non_manifest_dict_not_caught(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "cfg.py").write_text(
        'DB_CONFIG = {"host": "h", "port": 5432}\nDEFAULTS = {"a": 1}\n')
    contracts = set(scan_repo(str(d))["contracts"])
    assert "DB_CONFIG" not in contracts        # config dict, not a contract
    assert "DEFAULTS" not in contracts
    assert "Order" in contracts                 # real pydantic model still kept


def test_function_local_manifest_not_caught(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "local.py").write_text(
        'def build():\n    MANIFEST = {"name": "z"}\n    return MANIFEST\n')
    assert "MANIFEST" not in set(scan_repo(str(d))["contracts"])  # module-level only


def test_manifest_surfaces_in_map(tmp_path):
    from lib.archmap import render_architecture
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "plugin.py").write_text('MANIFEST = {"name": "funnel", "path": "/f"}\n')
    assert "MANIFEST" in render_architecture(str(d))
