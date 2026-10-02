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
