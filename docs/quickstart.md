# Начать за пять минут

Начните с одного своего небольшого Git-репозитория. Не запускайте пакет по всему диску.
Подставьте настоящий путь вместо `/path/to/your-project`; все команды ниже — из клона kit.

## 1. Посмотрите текущий контекст

Проверьте `git status`, существующие `AGENTS.md`/`CLAUDE.md`, команды тестов и владельца origin.
Чужой upstream-клон не является разрешением менять его. Сохраните незакоммиченные правки.

## 2. Добавьте каркас

```bash
python3 kit/scripts/ctx-scaffold.py /path/to/your-project --project your-project --no-justfile
```

Если `AGENTS.md` уже есть, добавьте `--additive`. Существующие правила не заменяются.
`--force` — явная перезапись; обычное внедрение обходится без него.

## 3. Заполните смысл и состояние

Создайте в своём проекте `docs/project.md`: зачем проект, для кого, что входит в scope.
Скопируйте `kit/templates/project.state.template` в корень своего проекта как `project.state`.
Замените placeholders реальными фактами, укажите `pointers.knowledge_entity: docs/project.md`.
Заполните `rules/stack.md`, `testing.md`, `boundaries.md`, `focus.md` и `migrations.md`.
Если `justfile` нужен — добавьте его из шаблона и замените все команды. Шаблон не является
готовым test runner. Scaffold сам state не создаёт: он не может знать правдивый next_action.

## 4. Проверьте и закоммитьте поимённо

```bash
python3 kit/scripts/project-state-validate.py --repo /path/to/your-project
python3 kit/scripts/ctx-lint.py /path/to/your-project --mode=block
```

Коммит содержит только просмотренные файлы. Не используйте `git add -A`.
Для solo/mainline: сначала коммит содержимого, затем stamp и отдельный state-коммит:

```bash
python3 kit/scripts/project-state-stamp.py --repo /path/to/your-project --next-action "Run the project checks and review adoption."
git -C /path/to/your-project add -- project.state
git -C /path/to/your-project commit -m "state: record the verified next step"
```

На feature-ветке существующий state не меняют; следующий шаг записывают в PR.
Для первоначального внедрения создайте state на default-ветке или согласуйте bootstrap
через PR: это одноразовое создание, а не регулярное штампование каждого PR.

## 5. Подключите хуки, если они полезны

Установите Gitleaks из [официального проекта](https://github.com/gitleaks/gitleaks).
На macOS: `brew install gitleaks`. Потом следуйте [руководству по хукам](hooks.md).

Начинайте с одного репозитория. После нескольких реальных задач решите, какие проверки
стоит сделать обязательными. Пакет не нужен целиком каждому текстовому проекту.
