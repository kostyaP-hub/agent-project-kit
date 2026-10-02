# Contributing

Keep the kit small, portable and useful in a real project. Discuss broad new runtime
adapters before implementation. Do not include private paths, credentials, client data,
transcripts or internal infrastructure in issues, examples, fixtures or pull requests.

1. Create a branch for one bounded change.
2. Preserve existing files and settings during adoption.
3. Add meaningful regression coverage for behavior and safety boundaries.
4. Run `python -m pytest -q kit/tests` and `python3 kit/scripts/public-check.py`.
5. Explain the user-visible change, evidence and limitations in the PR.
6. Do not stamp `project.state` on a feature branch. Put the next step under `## Дальше`.

Dependency commands and installation are explicit; no network calls inside hooks.
Public examples must be synthetic. Report security issues through private advisories.
