#!/usr/bin/env python3
"""Opt-in installation. Refuse collisions; uninstall only unchanged kit files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

KIT = Path(__file__).resolve().parents[1]
MARKER = '# agent-project-kit managed hook'
AGENT_COMMAND = 'python3 -B "$(git -C "$CLAUDE_PROJECT_DIR" rev-parse --path-format=absolute --git-common-dir)/agent-project-kit/scripts/agent-hook.py"'

def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], text=True, capture_output=True, timeout=10)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def wrapper(event):
    return f'''#!/bin/sh
{MARKER}
set -eu
kit_dir="$(git rev-parse --path-format=absolute --git-common-dir)/agent-project-kit"
exec python3 -B "$kit_dir/scripts/git-hook.py" {event}
'''

def claude_entry(event):
    return {'hooks': [{'type': 'command', 'command': AGENT_COMMAND + f' {event} --claude', 'timeout': 30}]}

def settings_data(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        raise ValueError('Claude settings must be an object with an object hooks field')
    for event in ('SessionStart', 'Stop'):
        if not isinstance(data.get('hooks', {}).get(event, []), list):
            raise ValueError(f'{event} must be a list')
    return data

def runtime_files():
    files = [p for part in ('lib', 'config', 'rules') for p in (KIT / part).rglob('*')
             if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts]
    files += [KIT / 'scripts' / name for name in (
        'git-hook.py', 'agent-hook.py', 'project-state-validate.py',
        'project-state-stamp.py', 'project-state-freshness.py')]
    return files

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--claude', action='store_true', help='also merge Claude Code local hooks')
    parser.add_argument('--uninstall', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    top = git(args.repo, 'rev-parse', '--show-toplevel')
    if top.returncode:
        raise ValueError('target is not a Git repository')
    repo = Path(top.stdout.strip()).resolve()
    common = Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip())
    gitdir = Path(git(repo, 'rev-parse', '--absolute-git-dir').stdout.strip())
    if common != gitdir:
        raise ValueError('install/uninstall from the primary checkout, not a linked worktree')
    custom = git(repo, 'config', '--get', 'core.hooksPath')
    if custom.returncode == 0:
        raise ValueError('core.hooksPath is configured; use the manual integration guide')
    runtime = common / 'agent-project-kit'
    manifest = runtime / 'install.json'
    hooks = {event: common / 'hooks' / event for event in ('pre-commit', 'pre-push')}
    settings = repo / '.claude' / 'settings.local.json'
    # All target paths must be regular local paths; do not follow redirected files.
    for path in [runtime, *hooks.values(), settings, settings.parent]:
        if path.is_symlink():
            raise ValueError('symlink target refused')
    if args.uninstall:
        if not manifest.is_file():
            raise ValueError('no kit installation manifest; nothing will be removed')
        saved = json.loads(manifest.read_text())
        existing = {str(p.relative_to(runtime)) for p in runtime.rglob('*') if p.is_file()}
        if any(p.is_symlink() for p in runtime.rglob('*')):
            raise ValueError('runtime has a symlink; preserve it and inspect manually')
        if existing != set(saved['files']) | {'install.json'}:
            raise ValueError('runtime has added/missing files; preserve it and inspect manually')
        for name, expected in saved['files'].items():
            if digest(runtime / name) != expected:
                raise ValueError('runtime modified; preserve it and inspect manually')
        for event, path in hooks.items():
            if not path.is_file() or path.read_text() != wrapper(event):
                raise ValueError('managed hook changed/missing; preserve it and inspect manually')
        data = settings_data(settings) if saved['claude'] else None
        if data is not None:
            for label, event in [('SessionStart', 'session-start'), ('Stop', 'stop')]:
                entries = data.get('hooks', {}).get(label, [])
                if claude_entry(event) not in entries:
                    raise ValueError('managed Claude entry changed/missing; inspect manually')
                entries.remove(claude_entry(event))
                if not entries:
                    data['hooks'].pop(label, None)
            if not data.get('hooks'):
                data.pop('hooks', None)
        print('REMOVE kit runtime and unchanged kit hooks; preserve other settings.')
        if args.dry_run:
            return 0
        if data is not None:
            if data or saved['settings_existed']:
                settings.write_text(json.dumps(data, indent=2) + '\n')
            else:
                settings.unlink()
        for path in hooks.values():
            path.unlink()
        shutil.rmtree(runtime)
        return 0
    if runtime.exists():
        if manifest.is_file():
            saved = json.loads(manifest.read_text())
            if args.claude and not saved['claude']:
                raise ValueError('installed Git-only; uninstall before changing profile')
            current_files = {str(p.relative_to(runtime)) for p in runtime.rglob('*') if p.is_file()}
            unchanged = current_files == set(saved['files']) | {'install.json'}
            unchanged &= all((runtime / name).is_file() and digest(runtime / name) == sha for name, sha in saved['files'].items())
            unchanged &= all(path.is_file() and path.read_text() == wrapper(event) for event, path in hooks.items())
            if saved['claude']:
                data = settings_data(settings)
                unchanged &= all(claude_entry(event) in data.get('hooks', {}).get(label, []) for label, event in [('SessionStart', 'session-start'), ('Stop', 'stop')])
            if unchanged:
                print('Already installed; no changes. Uninstall/reinstall to update the kit.')
                return 0
        raise ValueError('runtime exists or changed; will not overwrite')
    for path in hooks.values():
        if path.exists():
            raise ValueError('an existing hook would be replaced; use manual integration')
    data = settings_data(settings) if args.claude else None
    if not shutil.which('gitleaks'):
        raise ValueError('gitleaks is required; install it before enabling hooks')
    if data is not None:
        for label, event in [('SessionStart', 'session-start'), ('Stop', 'stop')]:
            entries = data.setdefault('hooks', {}).setdefault(label, [])
            if claude_entry(event) not in entries:
                entries.append(claude_entry(event))
    print('INSTALL local kit runtime, pre-commit/pre-push' + (' and Claude local hooks.' if args.claude else '.'))
    if args.dry_run:
        return 0
    files = {}
    runtime.mkdir()
    for source in runtime_files():
        relative = source.relative_to(KIT)
        dest = runtime / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        files[str(relative)] = digest(dest)
    (runtime / 'install.json').write_text(json.dumps({'version': 1, 'files': files,
        'claude': args.claude, 'settings_existed': settings.exists()}, indent=2) + '\n')
    for event, path in hooks.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wrapper(event))
        path.chmod(0o755)
    if data is not None:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2) + '\n')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        raise SystemExit(1)
