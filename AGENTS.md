---
project: agent-project-kit
load_strategy: alpha
---

# Agent Project Kit

Read `project.state`, README and the contract relevant to the task. This repository
contains public reusable tooling: no private workspace/vault/host/runtime information.

## Invariants

- CLI runtime: Python 3.11+, stdlib; pathspec is optional for .ctxignore.
- Hook installation is explicit, local and reversible; refuse existing Git hooks.
- Preserve existing policy and settings. Never silently overwrite on additive adoption.
- No network calls, telemetry, auto-commit, auto-push or production actions in hooks.
- Synthetic examples only. Never include private identity or connection data.
- Read the listed rule files explicitly if your runtime does not expand @ imports.
- Fresh checks before claims. Default-branch state has one writer; feature branch
  handoff belongs in PR under `## Дальше`.

## Verification

`python -m pytest -q kit/tests` and `python3 kit/scripts/public-check.py`.
Before publishing: Gitleaks on files and full Git history, independent content review,
then verify public clone and CI. See docs/publishing.md.

## Structure

`standard/`: contract. `kit/`: runtime, templates, examples, tests. `hooks/`: reference
wrappers. `docs/`: guides and playbook. Local ignored delivery/training files are not public.
