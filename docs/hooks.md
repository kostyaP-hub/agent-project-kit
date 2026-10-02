# Хуки: установка и отключение

Хуки opt-in. Клонирование kit ничего не включает. Installer не меняет глобальную
конфигурацию, не делает commit/push, не запускает сетевые запросы и project commands.
Поддерживаются primary checkouts на macOS/Linux с Python 3.11+, Git и Gitleaks 8.30.1+.

| Хук | Проверяет | Блокирует |
|---|---|---|
| pre-commit | Секреты в staged diff; staged state, если он изменён | Утечку, сбой сканера, невалидный state |
| pre-push | Секреты во всей локальной Git-истории; committed state каждого отправляемого ref | Утечку, отсутствие/устаревание anchor на mainline; изменение state в feature PR |
| SessionStart | Статус, следующий шаг, свежесть | Ничего; добавляет контекст |
| Stop | Незакоммиченные tracked changes и freshness | Просит закончить или объяснить оставшееся; при `stop_hook_active` не зацикливается |

Это не sandbox и не защита от злонамеренного пользователя. State freshness не проверяет
качество содержимого. Stop не читает transcript, не хранит его и не доказывает запуск тестов.
Он видит весь tracked diff, поэтому может попросить объяснить чужую оставшуюся работу;
не следует коммитить её ради зелёного хука.

## Git-хуки

Из клона kit:

```bash
python3 kit/scripts/install-hooks.py --repo /path/to/your-project --dry-run
python3 kit/scripts/install-hooks.py --repo /path/to/your-project
```

Runtime копируется в `.git/agent-project-kit/`, wrappers — в `.git/hooks/`.
Установка отказывается при существующих хуках, `core.hooksPath`, linked worktree,
symlink-целях, конфликте runtime или отсутствующем Gitleaks. Никакие старые хуки
не перезаписываются. Повторная установка не дублирует записи. Для обновления kit:
удалить неизменённую старую установку и установить новую.

Hooks действуют и при Git-командах в linked worktrees: их общий Git-directory тот же.
Installer запускается только из primary checkout. Изолированные git-dir layouts и Windows
не заявлены как поддерживаемые.

## Claude Code

```bash
python3 kit/scripts/install-hooks.py --repo /path/to/your-project --claude --dry-run
python3 kit/scripts/install-hooks.py --repo /path/to/your-project --claude
```

Добавляет только свои SessionStart/Stop entries в `.claude/settings.local.json`,
сохраняет остальные keys и hooks. Некорректный JSON останавливает установку до записи.
Runtime вызывается через Git-dir, пути с пробелами заключены в кавычки.
После установки проверьте `/hooks` и начните новую сессию по инструкции runtime.

Формат сверён с [официальной документацией Claude Code](https://code.claude.com/docs/en/hooks).
JSON-контракт проверяется тестами; автоматическое end-to-end испытание в живой Claude
сессии не выполнено. В некоторых средах требуется доверие к проекту или разрешение
локальных settings. Пакет не меняет permission policy агента.

## Другие агенты и ручной режим

`AGENTS.md` и команды проверки доступны любому агенту с shell. Автоматическая установка
Codex/Gemini/OpenClaw/Hermes hook adapters в этом выпуске не заявлена.

```bash
python3 -B kit/scripts/agent-hook.py session-start --repo /path/to/your-project
python3 -B kit/scripts/agent-hook.py stop --repo /path/to/your-project
```

## Существующий хук или hooksPath

Автоустановка откажется. Посмотрите [wrappers](../hooks/git/) и вручную добавьте вызов
`git-hook.py` к своему runner. Сохраните runtime в постоянном локальном пути, заключите
путь в кавычки и возвращайте ненулевой код при отказе проверки. Не вставляйте `|| true`.
Этот ручной workflow не поддерживается автоудалением kit.

## Удаление

```bash
python3 kit/scripts/install-hooks.py --repo /path/to/your-project --uninstall --dry-run
python3 kit/scripts/install-hooks.py --repo /path/to/your-project --uninstall
```

Удаляются только неизменённые managed wrappers и runtime, проверенные по manifest/hash.
Только добавленные этой установкой Claude entries удаляются по точному совпадению; остальные настройки сохраняются.
Изменённый хук, добавленные runtime-файлы или изменённая managed entry — отказ, без удаления.

Если проверка упала: исправьте причину. Не обходите хук ради успешного отчёта.
Истинный найденный секрет следует отозвать/заменить; удаление строки не отменяет утечку.
