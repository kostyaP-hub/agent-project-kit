"""P3 / F8 — opt-in auth-tier annotation from a literal PUBLIC_PATHS frozenset.

Trial verdict (X3): do NOT redact/edit admin routes — that gives obscurity, not
security, and breaks the drift gate (counts stop matching). Instead tag routes
`[public]`/`[auth]` from the repo's own literal PUBLIC_PATHS/PUBLIC_PREFIXES.
The constant NAME is repo-specific, so this is opt-in via ~/.ctx/config.json.
Annotation is render-only: facts["routes"] and signature_hash are unchanged.
"""
import json
import os
import shutil
from lib.config import load_config
from lib.extract import scan_repo
from lib.archmap import render_architecture, build_anchors

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def _with_auth(dst):
    (dst / "app" / "auth.py").write_text(
        'PUBLIC_PATHS = frozenset({"/health", "/contract"})\n'
        'PUBLIC_PREFIXES = ("/static",)\n')


# --- config opt-in --------------------------------------------------------
def test_config_auth_const_defaults_off(tmp_path):
    cfg = load_config(str(tmp_path / "none.json"))
    assert cfg["auth_public_const"] is None            # feature off by default
    assert cfg["auth_public_prefix_const"] is None


def test_config_loads_auth_const(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "auth_public_const": "PUBLIC_PATHS",
        "auth_public_prefix_const": "PUBLIC_PREFIXES",
    }))
    cfg = load_config(str(p))
    assert cfg["auth_public_const"] == "PUBLIC_PATHS"
    assert cfg["auth_public_prefix_const"] == "PUBLIC_PREFIXES"


# --- extraction -----------------------------------------------------------
def test_scan_extracts_public_paths(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    _with_auth(d)
    facts = scan_repo(str(d), auth_public_const="PUBLIC_PATHS",
                      auth_public_prefix_const="PUBLIC_PREFIXES")
    assert set(facts["public_paths"]) == {"/health", "/contract"}
    assert facts["public_prefixes"] == ["/static"]
    assert facts["auth_tier_active"] is True


def test_scan_auth_off_by_default(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    _with_auth(d)
    facts = scan_repo(str(d))                           # no const names passed
    assert facts["public_paths"] == []
    assert facts["auth_tier_active"] is False


def test_scan_missing_const_is_graceful(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)                             # no auth.py at all
    facts = scan_repo(str(d), auth_public_const="PUBLIC_PATHS")
    assert facts["auth_tier_active"] is False           # named const not found → no-op


# --- render annotation ----------------------------------------------------
def test_render_annotates_auth_tier(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    _with_auth(d)
    md = render_architecture(str(d), auth_public_const="PUBLIC_PATHS",
                             auth_public_prefix_const="PUBLIC_PREFIXES")
    assert "GET /health [public]" in md                 # in PUBLIC_PATHS
    assert "POST /orders [auth]" in md                  # not public → auth


def test_render_no_annotation_when_off(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    _with_auth(d)
    md = render_architecture(str(d))                    # opt-in off → zero behavior change
    assert "[public]" not in md and "[auth]" not in md
    assert "GET /health" in md


# --- gate integrity -------------------------------------------------------
def test_auth_tier_does_not_move_signature(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    _with_auth(d)
    off = build_anchors(scan_repo(str(d)))["signature_hash"]
    on = build_anchors(scan_repo(str(d), auth_public_const="PUBLIC_PATHS",
                                 auth_public_prefix_const="PUBLIC_PREFIXES"))["signature_hash"]
    assert off == on                                     # auth facts are not signature material
