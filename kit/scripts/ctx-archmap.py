#!/usr/bin/env python3
"""ctx-archmap — generate / check a repo's ARCHITECTURE.md legibility map.

    ctx-archmap.py <repo>            # print the map to stdout (preview)
    ctx-archmap.py <repo> --write    # write ARCHITECTURE.md + @-hookup into AGENTS.md
    ctx-archmap.py <repo> --check    # exit 1 if the map is stale/missing vs the code
    ctx-archmap.py <repo> --map docs/ARCHITECTURE.auto.md --write   # non-default location

The gate is stateless — no sidecar lock file is written or read.

Structure comes from the FACT of code (stdlib ast); the LLM never touches the fact
sections, so the map cannot hallucinate the architecture. Secrets are redacted (X3).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.archmap import render_architecture, write_map  # noqa: E402
from lib.lint import check_archmap  # noqa: E402
from lib.config import load_config  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Generate/check a repo ARCHITECTURE.md map.")
    ap.add_argument("repo")
    ap.add_argument("--write", action="store_true",
                    help="write the map + @-hookup into AGENTS.md")
    ap.add_argument("--check", action="store_true",
                    help="verify the map is fresh vs code; exit 1 if stale/missing")
    ap.add_argument("--project", default=None, help="project name (default: dir basename)")
    ap.add_argument("--map", default=None, dest="map_path", metavar="PATH",
                    help="map location relative to <repo> (default: ARCHITECTURE.md)")
    a = ap.parse_args()
    repo = os.path.abspath(os.path.expanduser(a.repo))
    if not os.path.isdir(repo):
        print(f"ERROR: not a directory: {repo}")
        return 2

    if a.check:
        r = check_archmap(repo, a.map_path)
        st, rel = r["status"], os.path.relpath(r["map"], repo)
        if st == "ok":
            print(f"[ok] {rel} fresh (signature {r['signature']})")
            return 0
        if st == "missing":
            print(f"[stale] no {rel} — run with --write")
            return 1
        if st == "no_anchor":
            print(f"[stale] {rel} has no ctx-archmap signature anchor")
            return 1
        print(f"[stale] map signature {r['found']} != code {r['expected']}; changed: {r['changed']}")
        return 1

    _cfg = load_config()  # F8 auth-tier constants are opt-in via ~/.ctx/config.json
    auth = (_cfg["auth_public_const"], _cfg["auth_public_prefix_const"])

    if a.write:
        res = write_map(repo, a.project, *auth, map_path=a.map_path)
        rel = os.path.relpath(res["map"], repo)
        print(f"WROTE {res['map']}")
        if res["hooked"] == "added":
            print(f"+ @./{rel} wired into AGENTS.md")
        elif res["hooked"] == "already":
            print(f"note: AGENTS.md already loads @./{rel}")
        else:
            print("note: no AGENTS.md hookup (run ctx-scaffold first to create AGENTS.md)")
        return 0

    print(render_architecture(repo, a.project, *auth))
    return 0


if __name__ == "__main__":
    sys.exit(main())
