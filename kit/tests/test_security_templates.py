"""Regression checks for the portable security baseline templates."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / "templates" / "security"


def load_yaml(path: Path) -> object:
    """Use macOS Ruby's standard Psych parser; this skill has no Python YAML dependency."""
    import yaml
    return yaml.safe_load(path.read_text())


def test_security_templates_parse() -> None:
    config = tomllib.loads((SECURITY / ".gitleaks.toml").read_text())
    assert config["extend"]["useDefault"] is True
    pre_commit = load_yaml(SECURITY / "pre-commit-config.yaml")
    workflow = load_yaml(SECURITY / "workflow-security.yml")
    assert pre_commit["repos"][0]["hooks"][0]["id"] == "gitleaks"
    assert workflow["jobs"]["gitleaks"]


def test_dependabot_template_has_valid_update_structure() -> None:
    config = load_yaml(SECURITY / "dependabot.yml")
    assert config["version"] == 2
    assert {item["package-ecosystem"] for item in config["updates"]} == {
        "pip", "npm", "github-actions"
    }
    for item in config["updates"]:
        assert item["directory"] == "/"
        assert item["schedule"]["interval"] == "weekly"


def test_actual_repository_ci_parses_and_shell_steps_are_valid() -> None:
    """Test the shipped workflow too: a YAML colon in an inline run broke CI."""
    import re
    ci = load_yaml(ROOT.parent / '.github/workflows/ci.yml')
    assert ci['permissions'] == {'contents': 'read'}
    matrix = ci['jobs']['test']['strategy']['matrix']
    assert set(matrix['os']) == {'ubuntu-latest', 'macos-latest'}
    assert set(matrix['python']) == {'3.11', '3.12'}
    for step in ci['jobs']['test']['steps']:
        if 'run' in step:
            command = re.sub(r'\$\{\{.*?\}\}', 'value', step['run'])
            subprocess.run(['bash', '-n', '-c', command], check=True, capture_output=True)
