"""X3 redaction — the required security gate for the code-legibility map.

The architecture map is generated from the FACT of code and may be committed /
synced to the vault. It must NEVER leak secret values, connection strings, or the
existence of credential files. These tests plant fake secrets and assert they are
stripped. (Spec v2 §5 X3.)
"""
from lib.redact import is_sensitive_filename, redact_value, redact_filenames


# ---- sensitive filenames (names, not contents, still must be hidden) ----

def test_env_files_are_sensitive():
    for name in (".env", ".env.production", ".env.local", "app/.env.prod"):
        assert is_sensitive_filename(name), name


def test_secret_and_key_files_are_sensitive():
    for name in ("secrets.json", "app/secrets.yaml", "id_rsa", "server.pem",
                 "mykey.key", "credentials.json", ".pgpass", "svc-account.json"):
        assert is_sensitive_filename(name), name


def test_ordinary_files_are_not_sensitive():
    for name in ("main.py", "app/core/config.py", "pyproject.toml",
                 "README.md", "docker-compose.yml", "package.json"):
        assert not is_sensitive_filename(name), name


# ---- connection strings / tokens scrubbed from any emitted string ----

def test_connection_strings_scrubbed():
    got = redact_value("db lives at postgres://user:pass@host:5432/prod plus redis://h:6379")
    assert "postgres://" not in got
    assert "pass@host" not in got
    assert "redis://" not in got
    assert "[redacted]" in got


def test_tokens_scrubbed():
    for secret in ("Authorization: Bearer abc.def.ghi123",
                   "key sk-ABCDEF0123456789abcdef",
                   "gho_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"):
        assert "[redacted]" in redact_value(secret)


def test_plain_text_untouched():
    s = "module broadcast has 3 public functions and 2 tables"
    assert redact_value(s) == s


# ---- filename list redaction (drop sensitive, keep the rest) ----

def test_redact_filenames_drops_sensitive():
    out = redact_filenames([".env.production", "app/main.py", "secrets.json", "pyproject.toml"])
    assert ".env.production" not in out
    assert "secrets.json" not in out
    assert "app/main.py" in out
    assert "pyproject.toml" in out
