"""P3 / F7 — route sub-grouping by path prefix (trial finding: 107/120 routes in
one main.py render as a flat wall; group them by prefix so the map navigates).

Grouping is a RENDER concern only — facts["routes"] and the signature_hash stay
identical, so the drift gate is untouched (X3: never edit the route inventory).
"""
import os
import shutil
from lib.extract import scan_repo
from lib.archmap import _group_routes, render_architecture, build_anchors

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_app")


def test_group_routes_by_two_segment_prefix():
    routes = [
        "GET /api/mkt/leads", "POST /api/mkt/campaigns",
        "GET /api/script/run", "GET /modules/funnel/ping",
        "GET /modules/funnel/api/data", "GET /health",
    ]
    groups = dict(_group_routes(routes))
    assert groups["/api/mkt"] == ["GET /api/mkt/leads", "POST /api/mkt/campaigns"]
    assert groups["/api/script"] == ["GET /api/script/run"]
    assert groups["/modules/funnel"] == [
        "GET /modules/funnel/ping", "GET /modules/funnel/api/data"]
    assert groups["/health"] == ["GET /health"]


def test_group_routes_root_and_empty():
    groups = dict(_group_routes(["GET /", "POST /orders"]))
    assert groups["/"] == ["GET /"]
    assert groups["/orders"] == ["POST /orders"]


def test_render_shows_route_groups(tmp_path):
    d = tmp_path / "app"
    shutil.copytree(FIX, d)
    (d / "app" / "routes_mkt.py").write_text(
        'from fastapi import FastAPI\napi = FastAPI()\n\n'
        '@api.get("/api/mkt/leads")\ndef a():\n    return 1\n\n'
        '@api.post("/api/mkt/campaigns")\ndef b():\n    return 1\n')
    md = render_architecture(str(d))
    assert "/api/mkt" in md                       # prefix header surfaces
    assert "GET /api/mkt/leads" in md             # full route still present (inventory intact)
    assert "POST /api/mkt/campaigns" in md


def test_grouping_does_not_move_signature():
    # F7 is render-only: the structural signature is derived from facts, not layout.
    facts = scan_repo(FIX)
    before = build_anchors(facts)["signature_hash"]
    render_architecture(FIX)                       # rendering must not mutate facts
    after = build_anchors(scan_repo(FIX))["signature_hash"]
    assert before == after
