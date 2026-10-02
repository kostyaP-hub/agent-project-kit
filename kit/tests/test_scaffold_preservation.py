from pathlib import Path
import subprocess
import sys

KIT = Path(__file__).resolve().parents[1]
SCRIPT = KIT / 'scripts/ctx-scaffold.py'

def test_existing_schema_survives_missing_example_config(tmp_path):
    repo = tmp_path / 'demo'
    repo.mkdir()
    (repo / 'config').mkdir()
    schema = repo / 'config/example.config.schema.json'
    original = '{"description":"Project-owned schema must survive"}\n'
    schema.write_text(original)
    result = subprocess.run([sys.executable, str(SCRIPT), str(repo), '--project', 'demo', '--no-justfile'],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert schema.read_text() == original
    assert (repo / 'config/example.config.json').exists()

def test_additive_keeps_project_rules_and_policy(tmp_path):
    repo = tmp_path / 'demo'
    repo.mkdir()
    (repo / 'rules').mkdir()
    agents = repo / 'AGENTS.md'
    agents.write_text('# Project-owned policy\n')
    rule = repo / 'rules/git.md'
    rule.write_text('# Project-owned rule\n')
    result = subprocess.run([sys.executable, str(SCRIPT), str(repo), '--project', 'demo', '--additive', '--no-justfile'],
                            text=True, capture_output=True)
    assert result.returncode == 0
    assert agents.read_text().startswith('# Project-owned policy\n')
    assert rule.read_text() == '# Project-owned rule\n'
