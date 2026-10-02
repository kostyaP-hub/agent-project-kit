"""config-as-data (spec v2 §Q3, ADOPT from ai-native-toolkit MIT).

Externalize scan-roots / owned-namespaces out of hardcode into ~/.ctx/config.json
(Codex critique: hardcoded SCAN_ROOTS/OWNED = fragility). Explicit owned list is
kept (no >=3-clone auto-learn — that would wrongly claim any public org).
"""
import json
import os
from lib.config import load_config, bootstrap_config


def test_defaults_when_no_file(tmp_path):
    cfg = load_config(str(tmp_path / "nope.json"))
    assert cfg["scan_roots"] == []
    assert cfg["owned"] == []
    assert cfg["knowledge_root"] is None
    assert cfg["knowledge_entity_glob"] == "projects/*.md"


def test_override_and_extras(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "owned_namespaces": ["acme"],
        "extra_namespaces": ["beta"],
        "excluded_paths": ["/some/path"],
        "knowledge_root": "~/knowledge",
        "knowledge_entity_glob": "wiki/projects/*.md",
    }))
    cfg = load_config(str(p))
    assert "acme" in cfg["owned"]          # override
    assert "beta" in cfg["owned"]          # extra merged in
    assert "/some/path" in cfg["excluded_paths"]
    assert cfg["knowledge_root"] == os.path.expanduser("~/knowledge")
    assert cfg["knowledge_entity_glob"] == "wiki/projects/*.md"


def test_bootstrap_writes_defaults(tmp_path):
    p = tmp_path / "c.json"
    bootstrap_config(str(p))
    assert p.exists()
    data = json.loads(p.read_text())
    assert "owned_namespaces" in data and "scan_roots" in data
    assert "knowledge_root" in data and "knowledge_entity_glob" in data
    # idempotent: does not clobber user edits
    data["extra_namespaces"] = ["mine"]
    p.write_text(json.dumps(data))
    bootstrap_config(str(p))
    assert json.loads(p.read_text())["extra_namespaces"] == ["mine"]
