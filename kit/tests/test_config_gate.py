"""config/ validate-only gate (spec v2 §Q3 part 2) — no jsonschema dep."""
from lib.lint import check_config

SCHEMA = '{"type":"object","required":["version"],"properties":{"version":{"type":"integer"}}}'


def _cfg(tmp_path, json_text, schema_text=None):
    d = tmp_path / "repo"
    (d / "config").mkdir(parents=True)
    (d / "config" / "app.json").write_text(json_text)
    if schema_text:
        (d / "config" / "app.schema.json").write_text(schema_text)
    return d


def test_valid_config_ok(tmp_path):
    assert check_config(str(_cfg(tmp_path, '{"version": 1}', SCHEMA))) == []


def test_missing_required_flagged(tmp_path):
    errs = [e for _, e in check_config(str(_cfg(tmp_path, '{"other": 1}', SCHEMA)))]
    assert any("version" in e for e in errs)


def test_invalid_json_flagged(tmp_path):
    errs = [e for _, e in check_config(str(_cfg(tmp_path, "{bad json", SCHEMA)))]
    assert any("JSON" in e for e in errs)


def test_wrong_type_flagged(tmp_path):
    errs = [e for _, e in check_config(str(_cfg(tmp_path, '{"version": "one"}', SCHEMA)))]
    assert any("version" in e for e in errs)


def test_json_without_schema_only_checks_validity(tmp_path):
    assert check_config(str(_cfg(tmp_path, '{"anything": true}'))) == []


def test_no_config_dir_ok(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    assert check_config(str(d)) == []
