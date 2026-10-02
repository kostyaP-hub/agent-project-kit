"""ctx-archmap — assemble a compact ARCHITECTURE.md from Layer A facts.

Provenance-split: ⚙️ fact sections are generated, 🧠 sections are TODO slots.
The map carries a signature_hash so a linter can catch drift deterministically.
"""
import os
import shutil
from lib.extract import scan_repo
from lib.archmap import render_architecture, build_anchors

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def test_render_has_sections_and_facts():
    md = render_architecture(FIX, project_name="sample-app")
    assert "sample-app" in md
    for marker in ("What it is", "Boundaries", "Entry points", "Commands"):
        assert marker in md
    assert "GET /health" in md and "POST /orders" in md
    assert "OrderStatus" in md          # FSM candidate surfaced
    assert "orders" in md               # db table
    assert "TODO" in md                 # human-intent slots exist
    assert "signature_hash" in md       # machine anchor embedded


def test_render_compact():
    # dumb-robust: the file stays small (compact-map principle; anchors are terse)
    assert len(render_architecture(FIX).splitlines()) <= 120


def test_render_redacts_sensitive_config(tmp_path):
    dst = tmp_path / "app"
    shutil.copytree(FIX, dst)
    (dst / ".env.production").write_text("DATABASE_URL=postgres://u:p@h:5432/db\n")
    (dst / "secrets.json").write_text("{}\n")
    md = render_architecture(str(dst))
    assert ".env.production" not in md
    assert "secrets.json" not in md
    assert "postgres://" not in md      # final redact pass scrubs any leaked value


def test_signature_stable():
    a = build_anchors(scan_repo(FIX))["signature_hash"]
    b = build_anchors(scan_repo(FIX))["signature_hash"]
    assert a == b


def test_signature_sensitive_to_structure():
    facts = scan_repo(FIX)
    base = build_anchors(facts)["signature_hash"]
    facts2 = dict(facts)
    facts2["routes"] = facts["routes"] + ["DELETE /orders/{id}"]
    assert build_anchors(facts2)["signature_hash"] != base
