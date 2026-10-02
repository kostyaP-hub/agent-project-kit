#!/usr/bin/env python3
"""Stamp project.state with the committed HEAD it describes."""
from __future__ import annotations
import argparse
import difflib
import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "project-state-validate.py"
FRESHNESS_PATH = ROOT / "lib" / "state_freshness.py"
STATE_NAMES = ("project.state", "project.state.yaml", "project.state.yml")

def load_validator():
    spec = importlib.util.spec_from_file_location("project_state_validate", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def load_freshness():
    spec = importlib.util.spec_from_file_location("state_freshness", FRESHNESS_PATH)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def git(repo, *args):
    try: return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired): return None

def quote(value): return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

def set_line(lines, key, value, after=None):
    prefix = key + ":"
    for i, line in enumerate(lines):
        if line.startswith(prefix): lines[i] = f"{key}: {value}" + ("\n" if line.endswith("\n") else ""); return
    if after:
        for i, line in enumerate(lines):
            if line.startswith(after + ":"):
                lines.insert(i + 1, f"{key}: {value}\n"); return
    lines.append(f"{key}: {value}\n")

def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--next-action"); p.add_argument("--status"); p.add_argument("--stage")
    p.add_argument("--allow-dirty", action="store_true"); p.add_argument("--allow-branch", action="store_true"); p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv); repo = args.repo.resolve()
    top = git(repo, "rev-parse", "--show-toplevel")
    if top is None or top.returncode: print("Ошибка: каталог не является Git-репозиторием.", file=sys.stderr); return 2
    repo = Path(top.stdout.strip()); state = next((repo / n for n in STATE_NAMES if (repo / n).is_file()), None)
    if not state: print("Ошибка: project.state не найден.", file=sys.stderr); return 2
    freshness = load_freshness()
    is_mainline, branch_label = freshness.default_branch_kind(repo, 10)
    if not is_mainline and not args.allow_branch and not args.dry_run:
        print(f"Ошибка: ветка {branch_label} — project.state штампуется только на default-ветке после мержа (единственным release-процессом). «Дальше» ветки пиши в PR, раздел «## Дальше». Обход: --allow-branch.", file=sys.stderr)
        return 2
    for name, limit in (("next_action", 200), ("stage", 120)):
        value = getattr(args, name)
        if value is not None and len(value) > limit:
            print(f"Ошибка: {name} длиннее {limit} символов.", file=sys.stderr); return 2
    dirty = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if dirty is None: print("Ошибка: не удалось проверить рабочее дерево.", file=sys.stderr); return 2
    paths = [x for x in dirty.stdout.split("\0") if len(x) > 3 and x[2] == " "]
    # Якорь описывает HEAD: мешают только правки отслеживаемых файлов. Неотслеживаемый мусор
    # (чужие черновики, выгрузки) не меняет HEAD — отказ из-за него приучил бы к --allow-dirty.
    tracked = [x for x in paths if not x.startswith("??") and x[3:] not in STATE_NAMES]
    untracked = [x[3:] for x in paths if x.startswith("??") and x[3:] not in STATE_NAMES]
    if tracked and not args.allow_dirty:
        print("Ошибка: есть незакоммиченный код; сначала закоммить код, потом штампуй.", file=sys.stderr); return 2
    if untracked:
        print(f"Предупреждение: неотслеживаемых файлов {len(untracked)} — якорь их не описывает.", file=sys.stderr)
    head = git(repo, "rev-parse", "HEAD")
    if head is None or head.returncode: print("Ошибка: у репозитория нет доступного HEAD.", file=sys.stderr); return 2
    original = state.read_text(encoding="utf-8"); lines = original.splitlines(keepends=True)
    set_line(lines, "updated", date.today().isoformat())
    # В кавычках: SHA из одних цифр (839011137388) YAML прочтёт как число, и валидатор его отвергнет.
    set_line(lines, "head_sha", quote(head.stdout.strip()[:12]), after="updated")
    if args.next_action is not None: set_line(lines, "next_action", quote(args.next_action))
    if args.status is not None: set_line(lines, "status", args.status)
    if args.stage is not None: set_line(lines, "stage", quote(args.stage))
    rendered = "".join(lines)
    if args.dry_run:
        sys.stdout.writelines(difflib.unified_diff(original.splitlines(True), rendered.splitlines(True), fromfile=str(state), tofile=str(state)))
        print("Проверка: project.state не изменён."); return 0
    state.write_text(rendered, encoding="utf-8")
    validator = load_validator()
    try: errors = validator.validate(validator.yaml_subset(rendered))
    except ValueError as exc: errors = [("$", str(exc))]
    if errors:
        state.write_text(original, encoding="utf-8")
        print("Ошибка: результат невалиден; исходный project.state восстановлен.", file=sys.stderr); return 1
    print(f"project.state проштампован: head_sha {head.stdout.strip()[:12]}.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
