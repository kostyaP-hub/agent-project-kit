import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "status-vocab-lint.py"

def run(entities):
    return subprocess.run([sys.executable, str(SCRIPT), "--entities", str(entities), "--report"], text=True, capture_output=True)

def test_fixture_statuses_are_mapped_and_active_needs_review(tmp_path):
    values = ["active", "draft", "in-progress", "parked", "superseded", "shipped"]
    for index, value in enumerate(values):
        (tmp_path / f"card-{index}.md").write_text(f"---\nstatus: {value}\n---\n")
    result = run(tmp_path)
    assert result.returncode == 0
    assert "| active | 1 | needs-review | active ничего не значит" in result.stdout
    assert "unknown: 0" in result.stdout

def test_unknown_status_is_reported(tmp_path):
    (tmp_path / "unknown.md").write_text("---\nstatus: invented-status\n---\n")
    result = run(tmp_path)
    assert "| invented-status | 1 | unknown |" in result.stdout
    assert "unknown: 1" in result.stdout

def test_fix_is_explicitly_not_implemented(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--entities", str(tmp_path), "--fix"], text=True, capture_output=True)
    assert result.returncode == 2
    assert result.stdout.strip() == "not implemented in v1"
