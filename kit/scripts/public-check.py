#!/usr/bin/env python3
"""Conservative publication checks. Complements Gitleaks and human review."""
from __future__ import annotations
import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PATHS = re.compile(r'(?:/Users/|/home/)[A-Za-z0-9_.-]+/|/root/[A-Za-z0-9_.-]+|(?:file|obsidian)://')
EMAIL = re.compile(r'(?<![\w\\])[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
IP = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')
WIKI = re.compile(r'\[\[[A-Za-zА-Яа-я][^\]\n]+\]\]')
PRIVATE_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.db', '.sqlite', '.sqlite3', '.zip', '.jsonl'}
PUBLIC_DIRS = ('standard', 'kit', 'hooks', 'docs', '.github')
SKIP = {'.venv', '__pycache__', '.pytest_cache', '.git', 'node_modules'}

def files(root):
    probe = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                           text=True, capture_output=True, timeout=10)
    if probe.returncode == 0 and Path(probe.stdout.strip()).resolve() == root.resolve():
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'],
                                capture_output=True, check=True, timeout=10)
        return [root / name.decode('utf-8') for name in result.stdout.split(b'\0') if name]
    return ([p for p in root.iterdir() if p.is_file()] +
            [p for name in PUBLIC_DIRS for p in (root / name).rglob('*')
             if p.is_file() and not any(part in SKIP for part in p.relative_to(root).parts)])

def findings(path, root, denylist):
    relative = path.relative_to(root)
    if path.is_symlink():
        return [(str(relative), 'symlink')]
    if path.suffix.lower() in PRIVATE_SUFFIXES or path.name in {'.env', 'credentials.json'}:
        return [(str(relative), 'sensitive-file-type')]
    if path.name.startswith('.env.') and path.name != '.env.example':
        return [(str(relative), 'environment-file')]
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeError, OSError):
        return [(str(relative), 'unreadable-or-binary')]
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        labels = []
        if PATHS.search(line): labels.append('private-path')
        if WIKI.search(line): labels.append('internal-wiki-link')
        for address in EMAIL.findall(line):
            domain = address.rsplit('@', 1)[1].lower()
            if address == 'git@github.com' and 'git@github.com:' in line:
                continue
            if domain not in {'example.com', 'example.org', 'example.net', 'users.noreply.github.com'}:
                labels.append('non-example-email')
        for value in IP.findall(line):
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            if not (address.is_loopback or any(address in ipaddress.ip_network(net) for net in
                    ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24'))):
                labels.append('non-documentation-ip')
        if any(value.casefold() in line.casefold() for value in denylist):
            labels.append('local-denylist-match')
        if labels:
            out.append((f'{relative}:{n}', ','.join(sorted(set(labels)))))
    return out

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--denylist', type=Path, help='local JSON string array; never commit this file')
    args = parser.parse_args(argv)
    denied = json.loads(args.denylist.read_text()) if args.denylist else []
    if not isinstance(denied, list) or not all(isinstance(x, str) and x for x in denied):
        parser.error('denylist must be a JSON array of non-empty strings')
    root = args.repo.resolve()
    targets = files(root)
    results = [item for path in targets for item in findings(path, root, denied)]
    for path, reason in results:
        print(f'{path}: {reason}')  # Deliberately omit the matched value.
    print(f'Publication check: {len(targets)} files; {len(results)} findings. Human review is still required.')
    return 1 if results else 0

if __name__ == '__main__':
    raise SystemExit(main())
