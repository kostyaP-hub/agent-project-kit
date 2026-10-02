#!/usr/bin/env python3
"""Validate project.state v1.4 without third-party dependencies.

The skill venv intentionally has neither PyYAML nor jsonschema.  This file
therefore parses only the documented project.state subset: mappings, scalar
values, and lists of mappings with two indentation levels below their parent.
It is not a general YAML parser; install-free, deterministic validation is the
reason for that boundary.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.config import load_config  # noqa: E402

CANONICAL = {"idea", "building", "live", "maintained", "paused", "superseded", "archived", "external"}
TOP = {"schema_version", "project", "status", "stage", "active_system", "updated", "pointers", "last_audit", "exceptions", "next_action", "blockers", "superseded_by", "head_sha"}
POINTERS = {"knowledge_entity", "vault_entity", "module_map", "architecture", "task_state", "roadmap", "release_contract", "decisions"}


def scalar(value: str) -> Any:
    value = value.strip()
    # Хвостовой комментарий у незакавыченного значения: "live   # пояснение" -> "live".
    # Внутри кавычек # остаётся частью строки, а "abc#1" не считается комментарием.
    if value[:1] not in ('"', "'"):
        value = re.sub(r"\s+#.*$", "", value).strip()
    if value in ("[]", "{}"):
        return [] if value == "[]" else {}
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def yaml_subset(text: str) -> dict[str, Any]:
    """Parse the small, indentation-based YAML subset accepted by this contract."""
    rows: list[tuple[int, str, int]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw:
            raise ValueError(f"line {number}: tabs are not supported")
        indent = len(raw) - len(raw.lstrip(" "))
        rows.append((indent, raw.strip(), number))

    def mapping(index: int, indent: int) -> tuple[dict[str, Any], int]:
        out: dict[str, Any] = {}
        while index < len(rows) and rows[index][0] == indent and not rows[index][1].startswith("- "):
            _, content, number = rows[index]
            if ":" not in content:
                raise ValueError(f"line {number}: expected key: value")
            key, raw_value = content.split(":", 1)
            if not key or key.strip() != key:
                raise ValueError(f"line {number}: invalid key")
            index += 1
            if raw_value.strip():
                out[key] = scalar(raw_value)
            elif index < len(rows) and rows[index][0] > indent:
                child_indent = rows[index][0]
                out[key], index = sequence(index, child_indent) if rows[index][1].startswith("- ") else mapping(index, child_indent)
            else:
                out[key] = None
        return out, index

    def sequence(index: int, indent: int) -> tuple[list[Any], int]:
        out: list[Any] = []
        while index < len(rows) and rows[index][0] == indent and rows[index][1].startswith("- "):
            _, content, number = rows[index]
            rest = content[2:].strip()
            index += 1
            if not rest:
                raise ValueError(f"line {number}: list item must be a mapping")
            if ":" not in rest:
                out.append(scalar(rest))
                continue
            key, raw_value = rest.split(":", 1)
            item = {key: scalar(raw_value)} if raw_value.strip() else {key: None}
            if index < len(rows) and rows[index][0] > indent:
                extra, index = mapping(index, rows[index][0])
                item.update(extra)
            out.append(item)
        return out, index

    if not rows:
        return {}
    result, end = mapping(0, rows[0][0])
    if end != len(rows):
        raise ValueError(f"line {rows[end][2]}: unexpected indentation or list item")
    return result


def is_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _is_within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((os.path.realpath(path), os.path.realpath(root))) == os.path.realpath(root)
    except ValueError:
        return False


def validate(data: Any, knowledge_root: str | None = None) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    def err(path: str, message: str) -> None: errors.append((path, message))
    if not isinstance(data, dict):
        return [("$", "must be an object")]
    for key in data:
        if key not in TOP: err(key, "additional property is not allowed")
    for key in ("schema_version", "project", "status", "updated", "pointers", "next_action"):
        if key not in data: err(key, "is required")
    if data.get("schema_version") != 1: err("schema_version", "must equal 1")
    if not isinstance(data.get("project"), str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", data.get("project", "")):
        err("project", "must be a kebab-case slug")
    if data.get("status") not in CANONICAL: err("status", "must be one of the canonical statuses")
    if "stage" in data and (not isinstance(data["stage"], str) or len(data["stage"]) > 120): err("stage", "must be a string of at most 120 characters")
    if "active_system" in data and not isinstance(data["active_system"], str): err("active_system", "must be a string")
    if not is_date(data.get("updated")): err("updated", "must be YYYY-MM-DD")
    if "head_sha" in data and (not isinstance(data["head_sha"], str) or not re.fullmatch(r"[0-9a-f]{7,40}", data["head_sha"])): err("head_sha", "must be 7-40 lowercase hexadecimal characters")
    pointers = data.get("pointers")
    if not isinstance(pointers, dict): err("pointers", "must be an object")
    else:
        for key in pointers:
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key): err(f"pointers.{key}", "additional property is not allowed")
        if not ({"knowledge_entity", "vault_entity"} & set(pointers)):
            err("pointers.knowledge_entity", "is required (карточка проекта в слое смысла)")
        for key, value in pointers.items():
            if not isinstance(value, str) or not value: err(f"pointers.{key}", "must be a non-empty path")
            elif value.startswith("/") and knowledge_root is not None and not _is_within(value, knowledge_root):
                err(f"pointers.{key}", "absolute paths must point into the knowledge root")
            elif not value.startswith("/") and (value.startswith("../") or "/../" in value): err(f"pointers.{key}", "must stay inside the repository")
    audit = data.get("last_audit")
    if audit is not None:
        if not isinstance(audit, dict): err("last_audit", "must be an object")
        else:
            for key in audit:
                if key not in {"sha", "date", "evidence"}: err(f"last_audit.{key}", "additional property is not allowed")
            for key in ("sha", "date", "evidence"):
                if key not in audit: err(f"last_audit.{key}", "is required")
            if "sha" in audit and (not isinstance(audit["sha"], str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", audit["sha"])): err("last_audit.sha", "must be 7-40 hexadecimal characters")
            if "date" in audit and not is_date(audit["date"]): err("last_audit.date", "must be YYYY-MM-DD")
            if "evidence" in audit and (not isinstance(audit["evidence"], str) or not audit["evidence"]): err("last_audit.evidence", "must be a non-empty path")
    for name, required in (("exceptions", {"id", "reason", "owner", "removal_condition"}), ("blockers", {"what", "owner"})):
        items = data.get(name)
        if items is None: continue
        if not isinstance(items, list): err(name, "must be a list")
        else:
            for i, item in enumerate(items):
                if not isinstance(item, dict): err(f"{name}[{i}]", "must be an object"); continue
                for key in item:
                    if key not in required: err(f"{name}[{i}].{key}", "additional property is not allowed")
                for key in required:
                    if key not in item: err(f"{name}[{i}].{key}", "is required")
                    elif not isinstance(item[key], str) or not item[key].strip(): err(f"{name}[{i}].{key}", "must be a non-empty string")
    action = data.get("next_action")
    if not isinstance(action, str) or not action.strip() or len(action) > 200: err("next_action", "must be a non-empty string of at most 200 characters")
    has_successor = "superseded_by" in data
    if data.get("status") == "superseded" and not has_successor: err("superseded_by", "is required when status is superseded")
    if data.get("status") != "superseded" and has_successor: err("superseded_by", "is allowed only when status is superseded")
    if has_successor and (not isinstance(data["superseded_by"], str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", data["superseded_by"])): err("superseded_by", "must be a kebab-case slug")
    return errors


def absolute_path_warnings(data: Any, repo: Path, knowledge_root: str | None) -> list[str]:
    """Warn about non-portable pointers only when no knowledge root is configured."""
    if knowledge_root is not None or not isinstance(data, dict) or not isinstance(data.get("pointers"), dict):
        return []
    return ["WARNING pointers.%s: absolute path outside repo — предпочитай путь относительно корня репо" % key
            for key, value in data["pointers"].items()
            if isinstance(value, str) and value.startswith("/") and not _is_within(value, str(repo))]


def locate(repo: Path) -> Path | None:
    for name in ("project.state", "project.state.yaml", "project.state.yml"):
        candidate = repo / name
        if candidate.is_file(): return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("path", nargs="?")
    group.add_argument("--repo", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.path) if args.path else locate(args.repo)
    if path is None:
        errors = [("$", "project.state, project.state.yaml, or project.state.yml was not found")]
        warnings: list[str] = []
        target = str(args.repo)
    else:
        target = str(path)
        data = {}
        knowledge_root = None
        try:
            data = yaml_subset(path.read_text(encoding="utf-8"))
            knowledge_root = load_config()["knowledge_root"]
            errors = validate(data, knowledge_root)
        except (OSError, ValueError) as exc: errors = [("$", str(exc))]
        warnings = absolute_path_warnings(data, args.repo or path.parent, knowledge_root)
        if path.exists() and len(path.read_text(encoding="utf-8").splitlines()) > 40:
            warnings.append(f"WARNING {target}: more than 40 lines ({len(path.read_text(encoding='utf-8').splitlines())})")
    if args.json:
        print(json.dumps({"valid": not errors, "path": target, "errors": [{"path": p, "message": m} for p, m in errors], "warnings": warnings}, ensure_ascii=False))
    else:
        for warning in warnings: print(warning)
        if errors:
            for field, message in errors: print(f"{field}: {message}")
        else: print(f"OK {target}")
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
