#!/usr/bin/env python3
"""Fail closed when Git content contains runtime secrets or private user data.

Modes:
  --staged    scan blobs about to be committed
  --worktree  scan tracked + untracked, non-ignored files in the current checkout
  --tracked   scan files tracked at HEAD
  --history   scan historical added lines for high-confidence secret formats
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import PurePosixPath
import re
import subprocess
import sys
from typing import Iterable

SAFE_ENV_TEMPLATE_NAMES = {'.env.example', '.env.demo', '.env.vps.example'}
PLACEHOLDER_WORDS = (
    'example', 'dummy', 'demo', 'test', 'placeholder', 'changeme', 'replace',
    'your_', 'your-', 'fake', '<', '${', 'localhost', '127.0.0.1', '...', '__'
)

# Historical synthetic sk-* fixtures that predate this gate. Hashes avoid
# publishing the fixture values themselves while keeping the exception exact.
_KNOWN_SYNTHETIC_TOKEN_SHA256 = {
    'e48babf9d456bd149a429acb22568c0d46ac32174daad9cbd3763a6f1307e628',
    '791debda1a050853d76e229268d996a175c72b1b9b534b7e8fdae7767d9fdadf',
    '16f1096cdb57a18e8792e006508eab14a1c98c0b2db4f1c5d302ace7fc93a3c2',
}

TOKEN_RULES: list[tuple[str, re.Pattern[str]]] = [
    ('GitHub token', re.compile(r'\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b')),
    ('Slack token', re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}\b')),
    ('AWS access key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('Google API key', re.compile(r'\bAIzaSy[0-9A-Za-z_-]{33}\b')),
    ('private key block', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('JWT literal', re.compile(r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b')),
    ('provider sk token', re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b')),
]
LITERAL_ASSIGNMENT = re.compile(
    r'''(?m)^[ \t]*([A-Z][A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|PRIVATE_KEY))[ \t]*=[ \t]*["']?([^"'\r\n#;]{12,})["']?[ \t]*$'''
)


def run(*args: str) -> bytes:
    return subprocess.check_output(args, stderr=subprocess.DEVNULL)


def forbidden_path(path: str) -> str | None:
    p = path.replace('\\', '/')
    while p.startswith('./'):
        p = p[2:]
    name = PurePosixPath(p).name
    low = p.lower()
    if name not in SAFE_ENV_TEMPLATE_NAMES and (
        name == '.env'
        or name.startswith('.env.')
        or name.endswith('.env')
        or ('.env.' in name and not name.endswith('.env.example'))
    ):
        return 'live environment file'
    if name in {'.npmrc', '.pypirc', '.netrc', 'git-credentials', 'credentials.json', 'client_secret.json', 'service-account.json', 'service_account.json'}:
        return 'credential/config file'
    private_runtime_prefixes = (
        'data/secrets/', 'data/state/', 'data/logs/', 'data/telemetry/', 'data/feedback/',
        'data/uploads/', 'data/support/', 'data/funnel/', 'data/store/', 'data/reports/',
        'data/customers/', 'data/customer/', 'data/sessions/', 'data/backups/', 'data/exports/',
        'data/chat/', 'data/private/', 'data/user-data/', 'data/user_data/',
        'aimarket-hub/data/',
    )
    if low.startswith(private_runtime_prefixes) or low in {'data/signups.json', 'data/users.json'}:
        return 'user/runtime data path'
    if re.search(r'\.(?:sqlite|sqlite3|db)(?:-wal|-shm)?$', low):
        return 'database file'
    if re.search(r'(?:^|/)[^/]+\.(?:before-[^/]+|pre-[^/]+|backup|orig|rej)$', low):
        return 'local backup/scratch file'
    if (
        name in {'id_rsa', 'id_ecdsa', 'id_ed25519', 'conductor_key'}
        or name.endswith(('_signing_key', '_private_key', '_secret_key'))
        or re.search(r'\.(?:pem|key|p12|pfx|jks)$', low)
    ):
        return 'private key/keystore file'
    return None


def looks_placeholder(value: str) -> bool:
    low = value.lower()
    if any(word in low for word in PLACEHOLDER_WORDS):
        return True
    # Shell/Python expressions are references/generators, not embedded credential literals.
    if '$' in value or '$(' in value or value.rstrip().endswith(('()', '):', ')')):
        return True
    if '\\' in value:
        return True
    return False


def scan_text(path: str, text: str, *, history: bool = False) -> list[str]:
    issues: list[str] = []
    for label, rx in TOKEN_RULES:
        for m in rx.finditer(text):
            value = m.group(0)
            if looks_placeholder(value):
                continue
            if hashlib.sha256(value.encode('utf-8')).hexdigest() in _KNOWN_SYNTHETIC_TOKEN_SHA256:
                continue
            issues.append(label)
            break
    if not history:
        for m in LITERAL_ASSIGNMENT.finditer(text):
            value = m.group(2).strip()
            if not looks_placeholder(value):
                issues.append(f'literal credential assignment ({m.group(1)})')
                break
    return sorted(set(issues))


def decode(blob: bytes) -> str | None:
    if b'\x00' in blob[:8192]:
        return None
    try:
        return blob.decode('utf-8')
    except UnicodeDecodeError:
        return blob.decode('utf-8', 'replace')


def staged_files() -> Iterable[tuple[str, bytes]]:
    raw = run('git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z')
    for bpath in raw.split(b'\0'):
        if not bpath:
            continue
        path = bpath.decode('utf-8', 'replace')
        try:
            yield path, run('git', 'show', f':{path}')
        except subprocess.CalledProcessError:
            continue


def worktree_files() -> Iterable[tuple[str, bytes]]:
    raw = run('git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    for bpath in raw.split(b'\0'):
        if not bpath:
            continue
        path = bpath.decode('utf-8', 'replace')
        try:
            yield path, open(path, 'rb').read()
        except OSError:
            continue


def tracked_files() -> Iterable[tuple[str, bytes]]:
    """Yield tracked HEAD blobs using one persistent cat-file process.

    Calling ``git show`` once per path made a pre-push scan take minutes on the
    monorepo. ``cat-file --batch`` gives the same committed bytes without a new
    Git process for every file.
    """
    raw = run('git', 'ls-tree', '-r', '-z', 'HEAD')
    entries: list[tuple[str, str]] = []
    for item in raw.split(b'\0'):
        if not item:
            continue
        try:
            meta, bpath = item.split(b'\t', 1)
            _mode, obj_type, oid = meta.decode('ascii').split()
        except (ValueError, UnicodeDecodeError):
            continue
        if obj_type != 'blob':
            continue
        entries.append((oid, bpath.decode('utf-8', 'replace')))

    proc = subprocess.Popen(
        ['git', 'cat-file', '--batch'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    assert proc.stdin is not None and proc.stdout is not None
    try:
        for oid, path in entries:
            proc.stdin.write((oid + '\n').encode('ascii'))
            proc.stdin.flush()
            header = proc.stdout.readline().decode('ascii', 'replace').strip()
            parts = header.split()
            if len(parts) != 3 or parts[1] != 'blob':
                continue
            try:
                size = int(parts[2])
            except ValueError:
                continue
            blob = proc.stdout.read(size)
            proc.stdout.read(1)  # trailing newline emitted by --batch
            yield path, blob
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.terminate()


def scan_files(items: Iterable[tuple[str, bytes]]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path, blob in items:
        why = forbidden_path(path)
        if why:
            findings.append((path, why))
            continue
        text = decode(blob)
        if text is None:
            continue
        for issue in scan_text(path, text):
            findings.append((path, issue))
    return findings


def scan_history() -> list[tuple[str, str]]:
    proc = subprocess.Popen(
        ['git', 'log', '--all', '--format=@@COMMIT %H', '--unified=0', '--no-ext-diff', '-p'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors='replace'
    )
    assert proc.stdout is not None
    commit = ''
    path = ''
    findings: set[tuple[str, str]] = set()
    for line in proc.stdout:
        if line.startswith('@@COMMIT '):
            commit = line.split()[1][:12]
            continue
        if line.startswith('+++ b/'):
            path = line[6:].strip()
            why = forbidden_path(path)
            if why:
                findings.add((f'{commit}:{path}', why))
            continue
        if not line.startswith('+') or line.startswith('+++'):
            continue
        body = line[1:]
        for issue in scan_text(path, body, history=True):
            findings.add((f'{commit}:{path}', issue))
    proc.wait()
    return sorted(findings)


def main() -> int:
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--staged', action='store_true')
    group.add_argument('--worktree', action='store_true')
    group.add_argument('--tracked', action='store_true')
    group.add_argument('--history', action='store_true')
    args = ap.parse_args()
    try:
        if args.staged:
            findings = scan_files(staged_files())
            label = 'staged changes'
        elif args.worktree:
            findings = scan_files(worktree_files())
            label = 'working tree'
        elif args.tracked:
            findings = scan_files(tracked_files())
            label = 'tracked repository'
        else:
            findings = scan_history()
            label = 'Git history'
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f'SECURITY GATE ERROR: could not scan repository: {exc}', file=sys.stderr)
        return 2

    if findings:
        print(f'SECURITY GATE BLOCKED: {len(findings)} issue(s) in {label}.', file=sys.stderr)
        for path, issue in findings[:80]:
            print(f'  - {path}: {issue}', file=sys.stderr)
        print('No secret values are printed. Remove/rotate the credential or move private data outside Git.', file=sys.stderr)
        return 1
    print(f'OK security gate: {label}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
