#!/usr/bin/env python3
"""Read-only status migration report for project cards in the knowledge layer; --fix is deliberately absent in v1."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


def load_vocab() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "config" / "status-vocab.json").read_text(encoding="utf-8"))


def statuses(entities: Path) -> Counter[str]:
    found: Counter[str] = Counter()
    for card in entities.rglob("*.md"):
        try:
            for line in card.read_text(encoding="utf-8", errors="replace").splitlines():
                match = re.match(r"^status:\s*(.*)$", line)
                if match: found[match.group(1).strip()] += 1
        except OSError:
            continue
    return found


def report(found: Counter[str], vocab: dict) -> str:
    mappings, canonical = vocab["mappings"], vocab["canonical"]
    rows = ["| значение | сколько карточек | канон или needs-review | подсказка |", "| --- | ---: | --- | --- |"]
    totals = Counter()
    for value in sorted(found):
        target = mappings.get(value, "unknown")
        totals["unknown" if target == "unknown" else "needs-review" if target == "needs-review" else "canonical"] += found[value]
        if target == "unknown": hint = "Добавьте явный mapping после проверки контекста."
        elif target == "needs-review": hint = vocab.get("special_hints", {}).get(value, vocab["needs_review_hint"])
        else: hint = canonical[target]
        safe_value, safe_hint = value.replace("|", "\\|"), hint.replace("|", "\\|")
        rows.append(f"| {safe_value or '(пусто)'} | {found[value]} | {target} | {safe_hint} |")
    rows.append(f"\ncanonical: {totals['canonical']}, needs-review: {totals['needs-review']}, unknown: {totals['unknown']}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entities", required=True, type=Path)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args(argv)
    if args.fix:
        print("not implemented in v1")
        return 2
    if not args.entities.is_dir():
        print(f"entities: not a directory: {args.entities}", file=sys.stderr)
        return 1
    found = statuses(args.entities)
    if args.report:
        print(report(found, load_vocab()))
    else:
        print(f"statuses: {sum(found.values())}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
