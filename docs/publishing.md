# Чеклист безопасной публикации

1. Сформируйте список разрешённых файлов. Не публикуйте рабочую папку целиком.
2. Исключите `.env`, доступы, БД, экспорты, raw ответы, отчёты клиентов, training/session
   progress, логи и старые архивы. Проверьте symlinks и скрытые файлы.
3. Замените рабочие примеры вымышленными. Удалите личные пути, адреса серверов,
   реальные email, внутренние ссылки, имена клиентов и рабочие ID.
4. Проверяйте секреты и приватность раздельно. Gitleaks ищет известные формы секретов;
   `public-check.py` — некоторые формы private paths, email, IP, wiki links и опасные файлы.
   Для своих названий передайте локальный `--denylist` (JSON array); не публикуйте этот файл.
5. Просмотрите каждый добавляемый файл; stage поимённо. Сканируйте всё содержимое и историю.
6. Не переносите `.git` из внутреннего проекта. Новый публичный проект получает чистый baseline.
7. Прогоните тесты из чистого клона без персональных конфигов. Проверьте install/uninstall.
8. Перед публикацией проведите независимое ревью. Зафиксируйте точный проверенный SHA.
9. Включите доступные secret scanning / push protection на GitHub, права Actions — contents:read.
10. После push проверьте public visibility, публичный клон, совпадение SHA и итог CI.

```bash
python3 kit/scripts/public-check.py
# После создания первого коммита:
gitleaks git . --log-opts=--all --redact --no-banner
```

Git author/committer metadata также публичны. Используйте нейтральную project identity
или публичный GitHub noreply email, если не хотите раскрывать личный email.

Нулевая выдача сканеров означает «в этих проверках ничего не найдено», а не математическое
доказательство отсутствия чувствительных данных. Scan policy и review остаются частью выпуска.

[GitHub secret scanning](https://docs.github.com/en/code-security/how-tos/secure-your-secrets/detect-secret-leaks/enable-secret-scanning) ·
[Что делать при утечке](https://docs.github.com/en/code-security/tutorials/remediate-leaked-secrets/remediating-a-leaked-secret)
