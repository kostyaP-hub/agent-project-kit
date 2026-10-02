"""config-as-data for the linter's own settings (spec v2 §Q3, port of ai-native-toolkit).

Scan-roots and owned git namespaces move out of hardcode into ~/.ctx/config.json.
Kept explicit (no >=3-clone auto-learn — that would wrongly claim any public org
you happen to have 3 clones of). `extra_*` survive a --bootstrap regenerate.
"""
import json
import os

CONFIG_PATH = os.path.expanduser("~/.ctx/config.json")

DEFAULTS = {
    "scan_roots": [],
    "owned_namespaces": [],
    "extra_roots": [],
    "extra_namespaces": [],
    "excluded_paths": [],
    # Слой смысла: где лежат карточки проектов. null = слоя нет, колонки entity/status
    # в отчёте будут прочерками. Пример: "~/second-brain/wiki" + "projects/*.md".
    "knowledge_root": None,
    "knowledge_entity_glob": "projects/*.md",
    # F8 (opt-in): names of the repo's literal public-route constants. None = off.
    # The constant NAME is repo-specific (e.g. PUBLIC_PATHS / PUBLIC_PREFIXES),
    # so auth-tier annotation stays off until a name is declared here.
    "auth_public_const": None,
    "auth_public_prefix_const": None,
}
_STRING_KEYS = ("auth_public_const", "auth_public_prefix_const", "knowledge_root",
                "knowledge_entity_glob")


def load_config(path=CONFIG_PATH):
    """Return resolved settings. Missing file => portable defaults."""
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            data = json.load(open(path, encoding="utf-8"))
            for k in DEFAULTS:
                if k not in data:
                    continue
                if isinstance(DEFAULTS[k], list) and isinstance(data[k], list):
                    cfg[k] = data[k]
                elif k in _STRING_KEYS and (isinstance(data[k], str) or data[k] is None):
                    cfg[k] = data[k]
        except (json.JSONDecodeError, OSError):
            pass
    roots = [os.path.expanduser(r) for r in cfg["scan_roots"] + cfg["extra_roots"]]
    owned = [x.lower() for x in cfg["owned_namespaces"] + cfg["extra_namespaces"]]
    excluded = [os.path.expanduser(p) for p in cfg["excluded_paths"]]
    return {"scan_roots": roots, "owned": owned, "excluded_paths": excluded,
            "auth_public_const": cfg["auth_public_const"],
            "auth_public_prefix_const": cfg["auth_public_prefix_const"],
            "knowledge_root": (os.path.expanduser(cfg["knowledge_root"])
                               if cfg["knowledge_root"] is not None else None),
            "knowledge_entity_glob": cfg["knowledge_entity_glob"]}


def bootstrap_config(path=CONFIG_PATH, force=False):
    """Write a default config if absent. Idempotent — never clobbers user edits."""
    if os.path.exists(path) and not force:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, indent=2, ensure_ascii=False)
    return path
