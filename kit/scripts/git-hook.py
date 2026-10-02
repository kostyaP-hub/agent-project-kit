#!/usr/bin/env python3
"""Small local gates. Never commit, stamp state, upload, or run project commands."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
from lib.state_freshness import check_revision

def run(args, repo, timeout=30):
    return subprocess.run(args, cwd=repo, timeout=timeout, check=False)

def main(argv=None, push_input=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('event', choices=['pre-commit', 'pre-push'])
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--git-stdin', action='store_true', help='read actual pushed refs from Git stdin')
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not shutil.which('gitleaks'):
        print('BLOCK: gitleaks is required. Install it before committing or pushing.', file=sys.stderr)
        return 1
    # Ignore repository/global allowlists: this gate uses the built-in scanner
    # rules with an explicitly empty supplemental config and ignore file.
    env = dict(os.environ)
    env.pop('GITLEAKS_CONFIG', None)
    env.pop('GITLEAKS_CONFIG_TOML', None)
    security = KIT / 'config' / 'hook-gitleaks.toml'
    scan = ['gitleaks', 'git', '--redact', '--no-banner', '--ignore-gitleaks-allow',
            '--config', str(security), '--gitleaks-ignore-path', str(KIT / 'config' / 'empty.gitleaksignore')]
    if args.event == 'pre-commit':
        scan += ['--pre-commit', '--staged']
    else:
        scan += ['--log-opts=--all']
    result = subprocess.run(scan + [str(repo)], cwd=repo, env=env, timeout=60, check=False)
    if result.returncode:
        return result.returncode
    if args.event == 'pre-commit':
        changed = subprocess.run(['git', '-C', str(repo), 'diff', '--cached', '--name-only', '-z',
                                  '--diff-filter=ACMR'], capture_output=True, check=True).stdout
        if b'project.state' in changed.split(b'\0'):
            # Validate staged bytes, not potentially different working-tree bytes.
            staged = subprocess.run(['git', '-C', str(repo), 'show', ':project.state'],
                                    text=True, capture_output=True, check=True).stdout
            import importlib.util
            spec = importlib.util.spec_from_file_location('state_validator', KIT / 'scripts' / 'project-state-validate.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            errors = module.validate(module.yaml_subset(staged))
            if len(staged.splitlines()) > 40:
                errors.append(('$', 'project.state exceeds 40 lines'))
            if errors:
                print('BLOCK: staged project.state is invalid.', file=sys.stderr)
                return 1
        return 0
    if args.git_stdin:
        records = sys.stdin.read(1024 * 1024 + 1) if push_input is None else push_input
        if len(records) > 1024 * 1024:
            raise ValueError('push input exceeds limit')
        targets = []
        for line in records.splitlines():
            fields = line.split()
            if len(fields) != 4:
                raise ValueError('invalid pre-push input')
            _, revision, destination, _ = fields
            if revision and set(revision) == {'0'}:
                continue  # Ref deletion does not send a commit.
            targets.append((revision, destination))
    else:
        branch = subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'],
                                text=True, capture_output=True, timeout=10)
        targets = [('HEAD', branch.stdout.strip() or None)]
    for revision, destination in targets:
        verdict = check_revision(repo, revision, destination)
        if verdict['status'] == 'feature_branch' and not verdict['state_touched']:
            continue
        if verdict['status'] != 'fresh':
            print(f"BLOCK: pushed project.state freshness = {verdict['status']}. Commit code, stamp state, commit state.", file=sys.stderr)
            return 1
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'BLOCK: local gate could not complete ({type(exc).__name__}).', file=sys.stderr)
        raise SystemExit(1)
