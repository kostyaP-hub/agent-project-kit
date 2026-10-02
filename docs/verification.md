# Проверка выпуска

## Локальная проверка

Полный набор: `python -m pytest -q kit/tests` — 149 passed на Python 3.12/macOS.
Проверка опубликованных файлов: `python3 kit/scripts/public-check.py` — 0 findings.
Gitleaks 8.30.1: staged baseline — no leaks found; full-history scan выполняется после коммитов.

Сценарии хуков: реальные commit/push gates, synthetic secret rejection, staged state
против отличающегося worktree, пути с пробелами, повторная установка, сохранение
существующих hooks/settings, отказ при изменённой установке, безопасное удаление,
SessionStart/Stop JSON и защита от stop-loop.

## Независимая проверка и CI

Перед публикацией обязателен отдельный read-only review. CI после push проверяет
Python 3.11/3.12 на macOS/Linux и всю Git-историю. Текущий результат CI виден в Actions;
бейдж не заменяет просмотр результата конкретного commit.

## Ограничения

Live-сессия Claude Code не проверена: сверены официальная схема и JSON-контракт.
Windows и автоматические adapters других агентов не заявлены. AST-карта главным образом
для Python. Scan result не является доказательством отсутствия любой private information;
примеры синтетические, публикация проходит отдельный контентный просмотр.
