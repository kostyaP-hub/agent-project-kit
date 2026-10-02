# Проверка выпуска

## Локальная проверка

Полный набор: `python -m pytest -q kit/tests` — 158 passed на Python 3.12/macOS.
Проверка опубликованных файлов: `python3 kit/scripts/public-check.py` — 0 findings.
Gitleaks 8.30.1: staged baseline — no leaks found; full-history scan выполняется после коммитов.

Сценарии хуков: реальные commit/push gates, synthetic secret rejection, staged state
против отличающегося worktree, пути с пробелами, повторная установка, сохранение
существующих hooks/settings, отказ при изменённой установке, безопасное удаление,
SessionStart/Stop JSON и защита от stop-loop.

Независимое ревью исходной версии выявило и помогло исправить parent-symlink,
проверку неправильного pushed revision, удаление pre-existing Claude entry,
перезапись существующей schema и неподтверждённое обещание branch guard.
Регрессии покрывают эти случаи, в том числе настоящим push в локальный bare remote.

## Независимая проверка и CI

Независимый read-only review основного kit и узкой CI-коррекции пройден.
Публичная копия baseline совпала с проверенной Git-историей; anonymous page/README вернули HTTP 200.
[Подтверждённый CI baseline](https://github.com/kostyaP-hub/agent-project-kit/actions/runs/37035628394)
для `1bc5d184f8c935f2aa3296268838a38c9ff7fce8`: все четыре matrix jobs успешны. CI после push проверяет
Python 3.11/3.12 на macOS/Linux и всю Git-историю. Текущий результат CI виден в Actions;
бейдж не заменяет просмотр результата конкретного commit.

## Ограничения

Live-сессия Claude Code не проверена: сверены официальная схема и JSON-контракт.
Windows и автоматические adapters других агентов не заявлены. AST-карта главным образом
для Python. Scan result не является доказательством отсутствия любой private information;
примеры синтетические, публикация проходит отдельный контентный просмотр.
