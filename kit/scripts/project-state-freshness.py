#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.state_freshness import check

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("repos", nargs="*", type=Path, default=[Path.cwd()])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on", default="stale")
    args = parser.parse_args(argv)
    failed = {item.strip() for item in args.fail_on.split(",") if item.strip()}
    results = [check(repo) for repo in args.repos]
    if args.json:
        print(json.dumps(results, ensure_ascii=False))
    else:
        for item in results:
            print(f"{item['repo']}: {item['status']} — {item['detail']}")
    return 1 if any(item["status"] in failed for item in results) else 0

if __name__ == "__main__":
    raise SystemExit(main())
