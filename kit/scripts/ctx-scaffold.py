#!/usr/bin/env python3
"""ctx-scaffold — раскатать инженерные правила в репозиторий.

Создаёт в <repo>:
  - AGENTS.md   (из templates/AGENTS.md.template, подстановка {{PROJECT}}/{{DESCRIPTION}})
  - CLAUDE.md   (тонкая обёртка: одна строка @AGENTS.md)
  - rules/      (копия rules/ из этого скилла — единый источник)
  - justfile    (из templates/justfile.template, если ещё нет)
  - docs/decisions/ (ADR README + 0000-template, если ещё нет)
  - .gitignore  (+ .worktrees/, если ещё нет)

Usage:
  ctx-scaffold.py <repo-path> [--project NAME] [--desc "текст"] [--force] [--no-justfile]

Не перезаписывает существующий AGENTS.md без --force (переименуй в AGENTS.md.legacy сам).
"""
import os
import sys
import shutil
import argparse

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_SRC = os.path.join(SKILL, "rules")
TEMPLATE = os.path.join(SKILL, "templates", "AGENTS.md.template")
JUSTFILE_TEMPLATE = os.path.join(SKILL, "templates", "justfile.template")
DECISIONS_TEMPLATE_DIR = os.path.join(SKILL, "templates", "decisions")

# --additive marker: a repo that already has a hand-written AGENTS.md keeps it and
# only gains the rule imports appended below this heading (idempotent, like the
# archmap @-hookup). --force would clobber content that is the repo's real value.
RULES_HEADING = "## Инженерные правила (engineering-rules)"
RULES_ORDER = ("git.md", "secrets.md", "worktree.md", "commits.md", "auth-payments.md",
               "stack.md", "testing.md", "boundaries.md", "focus.md")


def _append_rule_imports(agents_path):
    """Append the @./rules/*.md import block to an existing AGENTS.md. Idempotent."""
    txt = open(agents_path, encoding="utf-8").read()
    if RULES_HEADING in txt:
        return False
    if not txt.endswith("\n"):
        txt += "\n"
    txt += "\n" + RULES_HEADING + "\n" + "".join(f"@./rules/{f}\n" for f in RULES_ORDER)
    open(agents_path, "w", encoding="utf-8").write(txt)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--project", default=None)
    ap.add_argument("--desc", default="TODO: одна строка про проект")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--additive", action="store_true",
                    help="репо уже имеет свой AGENTS.md: сохранить его как есть, "
                         "дописать только @./rules/*.md + раскатать rules/GEMINI/CLAUDE")
    ap.add_argument("--no-justfile", action="store_true",
                    help="не создавать justfile")
    a = ap.parse_args()

    repo = os.path.abspath(os.path.expanduser(a.repo))
    if not os.path.isdir(repo):
        print(f"ERROR: не директория: {repo}")
        return 2
    project = a.project or os.path.basename(repo.rstrip("/"))

    agents = os.path.join(repo, "AGENTS.md")
    exists = os.path.exists(agents)
    if exists and not (a.force or a.additive):
        print(f"STOP: {agents} уже существует.")
        print("  --additive — сохранить его и дописать только @./rules/* (рекомендуется)")
        print("  --force    — ПЕРЕЗАПИСАТЬ шаблоном (потеряешь рукописный контент)")
        return 1

    if exists and a.additive:
        # keep the repo's own AGENTS.md — its hand-written content IS the value
        if _append_rule_imports(agents):
            print(f"+ @./rules/* дописаны в {agents} (контент сохранён)")
        else:
            print(f"= {agents} уже импортит rules/ — без изменений")
    else:
        # AGENTS.md из шаблона
        tpl = open(TEMPLATE, encoding="utf-8").read()
        tpl = tpl.replace("{{PROJECT}}", project).replace("{{DESCRIPTION}}", a.desc)
        open(agents, "w", encoding="utf-8").write(tpl)
        print(f"WROTE {agents}")

    # CLAUDE.md / GEMINI.md — тонкие обёртки @AGENTS.md (cross-CLI single-source).
    # Gemini CLI разворачивает @-import (Memory Import Processor, vN 0.41.2, вложенная
    # цепочка резолвится), Codex читает AGENTS.md нативно — один источник на все CLI.
    for wrapper in ("CLAUDE.md", "GEMINI.md"):
        wp = os.path.join(repo, wrapper)
        if os.path.exists(wp) and not a.force:
            print(f"  SKIP {wrapper} (существует; --force чтобы заменить на @AGENTS.md)")
        else:
            open(wp, "w", encoding="utf-8").write("@AGENTS.md\n")
            print(f"WROTE {wp} (@AGENTS.md)")

    # rules/ — копия единого источника
    dst_rules = os.path.join(repo, "rules")
    os.makedirs(dst_rules, exist_ok=True)
    n = 0
    for f in sorted(os.listdir(RULES_SRC)):
        if not f.endswith(".md"):
            continue
        dst = os.path.join(dst_rules, f)
        # не затирать уже заполненные stub'ы (stack/testing/boundaries/focus) без --force
        stub = f in {"stack.md", "testing.md", "boundaries.md", "focus.md"}
        if os.path.exists(dst) and not a.force:
            print(f"  SKIP rules/{f} (существует; --force чтобы перезаписать)")
            continue
        shutil.copy2(os.path.join(RULES_SRC, f), dst)
        n += 1
    print(f"COPIED {n} rules -> {dst_rules}/")

    # config/ — декларативный конфиг (пороги/контракты как data, не хардкод) + пример schema
    cfgdir = os.path.join(repo, "config")
    ex_json = os.path.join(cfgdir, "example.config.json")
    ex_schema = os.path.join(cfgdir, "example.config.schema.json")
    if not os.path.exists(ex_json):
        os.makedirs(cfgdir, exist_ok=True)
        open(ex_json, "w", encoding="utf-8").write(
            '{\n  "version": 1,\n  "thresholds": {}\n}\n')
        open(ex_schema, "w", encoding="utf-8").write(
            '{\n  "type": "object",\n  "required": ["version"],\n'
            '  "properties": {\n    "version": {"type": "integer"},\n'
            '    "thresholds": {"type": "object"}\n  }\n}\n')
        print(f"WROTE {cfgdir}/ (example config + schema — вынеси пороги/контракты сюда)")

    # .gitignore + .worktrees/
    gi = os.path.join(repo, ".gitignore")
    existing = open(gi, encoding="utf-8").read() if os.path.exists(gi) else ""
    if ".worktrees/" not in existing:
        with open(gi, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(".worktrees/\n")
        print(f"+ .worktrees/ в .gitignore")

    # Local DoD and ADR directory are additive: scaffolding must not replace a
    # project's real commands or decisions.
    if a.no_justfile:
        print("SKIP justfile (--no-justfile)")
    else:
        justfile = os.path.join(repo, "justfile")
        if os.path.exists(justfile):
            print("  SKIP justfile (существует)")
        else:
            shutil.copy2(JUSTFILE_TEMPLATE, justfile)
            print(f"WROTE {justfile}")

    decisions = os.path.join(repo, "docs", "decisions")
    os.makedirs(decisions, exist_ok=True)
    for name in ("README.md", "0000-template.md"):
        destination = os.path.join(decisions, name)
        if os.path.exists(destination):
            print(f"  SKIP docs/decisions/{name} (существует)")
        else:
            shutil.copy2(os.path.join(DECISIONS_TEMPLATE_DIR, name), destination)
            print(f"WROTE {destination}")

    print("\nГотово. Заполни rules/stack.md, rules/testing.md, rules/boundaries.md, rules/focus.md под проект.")
    print(f"Проверка: python3 {os.path.join(SKILL,'scripts','ctx-lint.py')} {repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
