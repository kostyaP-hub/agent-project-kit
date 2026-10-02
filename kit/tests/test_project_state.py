import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "project-state-validate.py"

def run(path):
    env = dict(os.environ, HOME=str(Path(path).parent / "home-without-ctx"))
    return subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True, capture_output=True, env=env)

def valid_text(extra=""):
    return """schema_version: 1
project: example-project
status: live
updated: 2026-09-08
pointers:
  vault_entity: /shared/wiki/projects/example-project.md
next_action: Keep the contract current.
""" + extra

def test_examples_are_valid():
    for name in ("project.state.recipe-calculator.yaml", "project.state.ads-studio.yaml"):
        result = run(ROOT / "examples" / name)
        assert result.returncode == 0, result.stdout + result.stderr

def test_invalid_contracts(tmp_path):
    cases = {
        "unknown": valid_text("unexpected: value\n"),
        "empty-action": valid_text().replace("Keep the contract current.", ""),
        "bad-status": valid_text().replace("status: live", "status: shipping"),
        "no-successor": valid_text().replace("status: live", "status: superseded"),
        "wrong-successor": valid_text("superseded_by: replacement\n"),
        "exception-owner": valid_text("exceptions:\n  - id: x\n    reason: temporary\n    removal_condition: remove later\n"),
    }
    for name, content in cases.items():
        path = tmp_path / name
        path.write_text(content)
        assert run(path).returncode == 1, name

def test_long_file_warns_but_is_valid(tmp_path):
    path = tmp_path / "project.state"
    path.write_text(valid_text("\n" * 41))
    result = run(path)
    assert result.returncode == 0
    assert "WARNING" in result.stdout

def test_repo_option_finds_state(tmp_path):
    (tmp_path / "project.state.yaml").write_text(valid_text())
    env = dict(os.environ, HOME=str(tmp_path / "home-without-ctx"))
    result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(tmp_path)], text=True, capture_output=True, env=env)
    assert result.returncode == 0

def test_decisions_pointer_is_optional_and_valid(tmp_path):
    path = tmp_path / "project.state"
    path.write_text(valid_text().replace(
        "next_action:", "  decisions: docs/decisions\nnext_action:"))
    assert run(path).returncode == 0


def test_absolute_pointer_warns_without_knowledge_root(tmp_path):
    path = tmp_path / "project.state"
    path.write_text(valid_text())
    result = run(path)
    assert result.returncode == 0
    assert "absolute path outside repo" in result.stdout


def _load_module():
    spec = importlib.util.spec_from_file_location("project_state_validate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_inline_comment_is_stripped_from_unquoted_scalar():
    """Агент пишет "status: live  # пояснение" — валидный YAML, должен приниматься."""
    data = _load_module().yaml_subset(
        'schema_version: 1\n'
        'project: demo   # имя папки\n'
        'status: live  # idea | building | live\n'
        'stage: "путь к #3 в списке"\n'
    )
    assert data["status"] == "live"
    assert data["project"] == "demo"
    assert data["stage"] == "путь к #3 в списке"
