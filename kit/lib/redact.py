"""X3 redaction — security gate for the code-legibility map (spec v2 §5).

The architecture map is generated from the FACT of code and may be committed or
synced to the vault. It must NEVER leak secret VALUES, connection strings, or the
existence of credential files. Redaction is deliberately FAIL-SAFE: over-redacting
a filename in the map costs nothing (the file still exists on disk), leaking one
can hand an attacker a map. So the filename denylist is intentionally generous.
"""
import os
import re
from fnmatch import fnmatch

# Filenames whose mere NAME should not appear in a shared map. Fail-safe: broad.
SENSITIVE_FILE_PATTERNS = (
    ".env", ".env.*",
    "*secret*", "*credential*", "*password*", "*passwd*", "*token*",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "*.ovpn",
    "*apikey*", "*api_key*", "*_key.*", "*key*.json",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    ".pgpass", "*.pgpass", ".htpasswd",
    "*account*.json", "*service-account*", "*svc-account*",
)

# Connection strings carrying host/creds — scrub whole token up to whitespace.
_DB_URI = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|redis(?:s)?|mongodb(?:\+srv)?|amqps?|"
    r"mssql|sqlserver|jdbc:[a-z0-9]+|memcached)://\S+",
    re.IGNORECASE,
)
# Any URI that embeds user:pass@ credentials, regardless of scheme.
_CRED_URI = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s@]+@\S+", re.IGNORECASE)
# Bearer / API-key / JWT shapes.
_TOKENS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),                                   # OpenAI-style
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),                            # GitHub PAT
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                                    # AWS access key id
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),                         # Slack
)

REDACTED = "[redacted]"


def is_sensitive_filename(name: str) -> bool:
    """True if a filename should be hidden from a shared map (matched on basename)."""
    base = os.path.basename(str(name)).lower()
    return any(fnmatch(base, pat) for pat in SENSITIVE_FILE_PATTERNS)


def redact_value(s: str) -> str:
    """Scrub connection strings and token shapes from an arbitrary string."""
    out = _DB_URI.sub(REDACTED, s)
    out = _CRED_URI.sub(REDACTED, out)
    for rx in _TOKENS:
        out = rx.sub(REDACTED, out)
    return out


def redact_filenames(names):
    """Drop sensitive filenames from a list, preserving order of the rest.

    Callers should report the dropped count so the map is not a silent truncation.
    """
    return [n for n in names if not is_sensitive_filename(n)]
