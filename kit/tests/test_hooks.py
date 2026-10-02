"""Real Git boundaries and reversible installation, including failure scenarios."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

KIT = Path(__file__).resolve().parents[1]
SCRIPTS = KIT / 'scripts'

def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], text=True, capture_output=True, check=check)

def repo(tmp_path):
    root = tmp_path / 'project with spaces'
    root.mkdir()
    git(root, 'init', '-b', 'main')
    git(root, 'config', 'user.name', 'Test')
    git(root, 'config', 'user.email', 'test@example.com')
    (root / 'code.txt').write_text('example\n')
    git(root, 'add', '--', 'code.txt')
    git(root, 'commit', '-m', 'initial')
    anchor = git(root, 'rev-parse', 'HEAD').stdout.strip()[:12]
    (root / 'project.state').write_text(f'''schema_version: 1
project: example-project
status: building
updated: 2026-01-01
head_sha: "{anchor}"
pointers:
  knowledge_entity: docs/project.md
next_action: Run the checks.
''')
    git(root, 'add', '--', 'project.state')
    git(root, 'commit', '-m', 'state')
    return root

def install(root, *args):
    return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'install-hooks.py'),
                           '--repo', str(root), *args], text=True, capture_output=True)

@pytest.fixture(autouse=True)
def no_personal_git_environment(tmp_path, monkeypatch):
    # Tests must not pick up personal hooks, signing, templates or Git identity.
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(tmp_path / 'empty-gitconfig'))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_TEMPLATE_DIR', str(tmp_path / 'empty-template'))

def test_dry_run_existing_hook_and_hooks_path_preserved(tmp_path):
    root = repo(tmp_path)
    assert install(root, '--dry-run').returncode == 0
    assert not (root / '.git/agent-project-kit').exists()
    old = root / '.git/hooks/pre-commit'
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text('#!/bin/sh\nexit 0\n')
    before = old.read_bytes()
    result = install(root)
    assert result.returncode == 1 and 'existing hook' in result.stderr
    assert old.read_bytes() == before and not (root / '.git/agent-project-kit').exists()
    old.unlink()
    git(root, 'config', 'core.hooksPath', 'custom-hooks')
    assert install(root).returncode == 1
    assert git(root, 'config', '--get', 'core.hooksPath').stdout.strip() == 'custom-hooks'

def test_install_idempotent_and_uninstall_preserves_settings(tmp_path):
    root = repo(tmp_path)
    settings = root / '.claude/settings.local.json'
    settings.parent.mkdir()
    original = {'permissions': {'allow': []}, 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo local'}]}]}}
    settings.write_text(json.dumps(original))
    assert install(root, '--claude').returncode == 0
    once = settings.read_bytes()
    assert install(root, '--claude').returncode == 0
    assert settings.read_bytes() == once
    # Exercise the actual installed wrapper (including a path with spaces).
    (root / 'code.txt').write_text('changed\n')
    git(root, 'add', '--', 'code.txt')
    assert git(root, 'commit', '-m', 'change').returncode == 0
    assert install(root, '--uninstall', '--dry-run').returncode == 0
    assert (root / '.git/hooks/pre-commit').exists()
    assert install(root, '--uninstall').returncode == 0
    assert json.loads(settings.read_text()) == original
    assert not (root / '.git/hooks/pre-commit').exists()
    assert not (root / '.git/agent-project-kit').exists()

def test_uninstall_refuses_modified_runtime_or_hook(tmp_path):
    root = repo(tmp_path)
    assert install(root).returncode == 0
    path = root / '.git/hooks/pre-commit'
    original = path.read_text()
    path.write_text(original + '# changed\n')
    assert install(root, '--uninstall').returncode == 1
    assert path.exists() and (root / '.git/hooks/pre-push').exists()
    path.write_text(original)
    extra = root / '.git/agent-project-kit/local.txt'
    extra.write_text('must survive')
    assert install(root, '--uninstall').returncode == 1
    assert extra.read_text() == 'must survive'

def test_invalid_settings_and_symlink_refused_before_mutation(tmp_path):
    root = repo(tmp_path)
    settings = root / '.claude/settings.local.json'
    settings.parent.mkdir()
    settings.write_text('invalid json')
    assert install(root, '--claude').returncode == 1
    assert not (root / '.git/agent-project-kit').exists()
    settings.unlink()
    settings.symlink_to(tmp_path / 'outside.json')
    assert install(root, '--claude').returncode == 1
    assert not (root / '.git/agent-project-kit').exists()

def test_worktree_install_refused(tmp_path):
    root = repo(tmp_path)
    worktree = tmp_path / 'linked'
    git(root, 'worktree', 'add', '-b', 'feature', str(worktree))
    assert install(worktree).returncode == 1
    assert not (root / '.git/agent-project-kit').exists()

def test_staged_invalid_state_blocked_even_with_valid_worktree(tmp_path):
    root = repo(tmp_path)
    assert install(root).returncode == 0
    state = root / 'project.state'
    original = state.read_text()
    state.write_text(original.replace('status: building', 'status: invalid'))
    git(root, 'add', '--', 'project.state')
    state.write_text(original)
    got = git(root, 'commit', '-m', 'bad staged state', check=False)
    assert got.returncode != 0 and 'staged project.state is invalid' in got.stderr

def test_real_secret_is_blocked_and_not_printed(tmp_path):
    root = repo(tmp_path)
    assert install(root).returncode == 0
    # Deliberately constructed synthetic value; never a credential issued by a provider.
    fake = 'gh' + 'p_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'
    (root / 'secret.txt').write_text('token = "' + fake + '"\n')
    git(root, 'add', '--', 'secret.txt')
    got = git(root, 'commit', '-m', 'unsafe fixture', check=False)
    assert got.returncode != 0 and fake not in got.stdout + got.stderr

def test_pre_push_blocks_stale_and_accepts_feature(tmp_path):
    root = repo(tmp_path)
    module = load('git-hook')
    assert module.main(['pre-push', '--repo', str(root)]) == 0
    (root / 'code.txt').write_text('change\n')
    git(root, 'commit', '-am', 'change')
    assert module.main(['pre-push', '--repo', str(root)]) == 1
    git(root, 'remote', 'add', 'origin', 'https://example.com/owner/project.git')
    git(root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    git(root, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
    git(root, 'checkout', '-b', 'feature')
    assert module.main(['pre-push', '--repo', str(root)]) == 0
    (root / 'project.state').write_text((root / 'project.state').read_text().replace('Run the checks.', 'Changed.'))
    git(root, 'commit', '-am', 'bad branch state')
    assert module.main(['pre-push', '--repo', str(root)]) == 1

def test_agent_protocol_and_no_stop_loop(tmp_path):
    root = repo(tmp_path)
    script = SCRIPTS / 'agent-hook.py'
    def call(event, **extra):
        payload = {'cwd': str(root), **extra}
        got = subprocess.run([sys.executable, '-B', str(script), event, '--claude'],
                             input=json.dumps(payload), text=True, capture_output=True)
        assert got.returncode == 0, got.stderr
        return json.loads(got.stdout)
    start = call('session-start')
    assert start['hookSpecificOutput']['hookEventName'] == 'SessionStart'
    assert call('stop') == {}
    (root / 'code.txt').write_text('uncommitted\n')
    assert call('stop')['decision'] == 'block'
    assert call('stop', stop_hook_active=True) == {}

def test_missing_scanner_is_blocking(tmp_path, monkeypatch):
    root = repo(tmp_path)
    module = load('git-hook')
    monkeypatch.setattr(module.shutil, 'which', lambda _: None)
    assert module.main(['pre-commit', '--repo', str(root)]) == 1

def test_reference_wrappers_match_installer():
    module = load('install-hooks')
    for event in ('pre-commit', 'pre-push'):
        assert (KIT.parent / 'hooks/git' / event).read_text() == module.wrapper(event)
