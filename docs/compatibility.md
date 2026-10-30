# Совместимость: кто что читает

Сверено с документацией 30.10.2026. Агенты меняются быстро: перед опорой на строку
откройте источник. Kit держит один канон — `AGENTS.md`; остальные файлы — обёртки.

| Агент | Читает `AGENTS.md` | Вложенные файлы | Как подключить kit | Источник |
|---|---|---|---|---|
| Codex CLI | Да, нативно | Да: от корня до текущей папки, ближний файл идёт позже и перекрывает; `AGENTS.override.md` в той же папке заменяет `AGENTS.md` | Ничего не нужно | [Codex: AGENTS.md](https://developers.openai.com/codex/guides/agents-md) |
| Claude Code | Да, встроенным плагином. По умолчанию — только если в проекте нет своего `CLAUDE.md`; режим `claude-md-and-agents-md` грузит оба | Да, как `CLAUDE.md` | Обёртка `CLAUDE.md` с одной строкой `@AGENTS.md`. Импортированный файл повторно не грузится | [anthropics/claude-code: agents-md](https://github.com/anthropics/claude-code/blob/main/mods/agents-md/README.md) |
| GitHub Copilot (CLI, VS Code, GitHub.com) | Да, вместе с `CLAUDE.md` и `GEMINI.md` | Зависит от клиента | Ничего не нужно. Общего порядка приоритета между файлами инструкций в большинстве клиентов нет — не дублируйте правила в `.github/copilot-instructions.md` | [GitHub Docs: custom instructions](https://docs.github.com/en/copilot/concepts/prompting-and-context/custom-instructions) |
| Gemini CLI | По умолчанию читает `GEMINI.md`; `AGENTS.md` — через `context.fileName` в `settings.json` | Да: предки рабочей папки и папки, к которым обращается инструмент | Обёртка `GEMINI.md` с `@AGENTS.md` или `"context": {"fileName": ["AGENTS.md", "GEMINI.md"]}` | [Gemini CLI: GEMINI.md](https://geminicli.com/docs/cli/gemini-md/) |

## Что из этого следует

- **Один канон, тонкие обёртки.** Не копируйте содержимое `AGENTS.md` в `CLAUDE.md`
  или `GEMINI.md`: копии расходятся. `ctx-lint` проверяет обёртки.
- **Не смешивайте системы инструкций.** Если правило есть и в `AGENTS.md`, и в
  `.github/copilot-instructions.md`, агент получит оба без гарантии, какое победит.
- **Вложенный `AGENTS.md` — для чужих правил модуля**, а не для повтора корневых.
- **Хуки не переносимы.** События и форматы у Claude Code, Codex и Gemini CLI разные.
  Kit поставляет пример только для Claude Code; для остальных — ручные команды
  (`project-state-validate.py`, `ctx-lint.py`). См. [хуки](hooks.md).
- **Импорт `@file` разворачивают не все.** Если ваш агент его не понимает, он должен
  прочитать `AGENTS.md` явно — это записано в [стандарте](../standard/01-PROJECT-STANDARD.md).
