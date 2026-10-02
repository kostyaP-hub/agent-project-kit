# Правило: worktree (изоляция параллельной работы)

- Перед первой write-операцией Execution-сессии — `git worktree list`. Если есть >1 активный worktree ИЛИ работа трогает shared-файлы (registry, главный API, миграции в одной нумерации) — работай в **отдельном worktree** с первого коммита.
- Worktree создавай **внутри `<repo>/.worktrees/<branch-name>/`**, не в глобальной директории — иначе ломается локальность и cleanup.
- Добавь `.worktrees/` в `.gitignore` (один раз).
- Если пакет установлен editable (`__editable__*.pth` в .venv) — в worktree нужен **свой venv** (`python -m venv .venv && pip install -e ".[dev]"`), иначе тесты worktree импортируют код главного checkout.
- Ветвиться **от `origin/main`, не от HEAD**: `git fetch origin && git worktree add .worktrees/<branch> -b <branch> origin/main`. В общем checkout HEAD может нести чужие коммиты параллельной сессии.
- **Жизненный цикл: worktree живёт до merge и умирает в той же сессии.** После merge — `git worktree remove <path>` + `git branch -d <branch>`. Не оставляй worktree «на потом»: брошенные копии путают агентов и забивают диск.
- Еженедельный отчёт помечает worktree старше 14 дней. Незамерженные или грязные — только в отчёт, решает человек; замерженные и чистые удаляются поимённо (`git worktree remove`, никогда `rm -rf` по маске).
- Branch без worktree от коллизий НЕ защищает: рабочая директория и HEAD общие.
