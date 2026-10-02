#!/usr/bin/env python3
"""Scan public source and recursively expanded release assets without extraction."""
import argparse
import io
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path

PRIVATE = re.compile(rb"192\.168\.|\b10\.[0-9]+\.[0-9]+\.[0-9]+|\b172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+|\b(?:Michael|Olivia|Preston|ms01)\b|asdk_app_[a-z0-9]+|6abd[0-9a-f]{20,}|chatgpt\.com/c/|/root/rackmarshal|/var/lib/homelab|/data/family|homelab-backups|weekly-homelab", re.I)
SECRET = re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}")
EXCLUDED = ("internal/", "evals/results/", "packaging/chatgpt-business/")
errors = []
count = 0

def scan(name, data):
    global count
    count += 1
    member = name.rsplit("!", 1)[-1]
    parts = Path(member).parts
    if any(x.startswith('..') for x in parts) or Path(member).is_absolute():
        errors.append((name, 'unsafe member path'))
    if any(x in parts for x in ('.git', 'chatgpt-business', 'internal')) or 'evals/results/' in name:
        errors.append((name, 'private path'))
    suffix = Path(member).suffix.lower()
    if suffix in ('.env', '.pem', '.key', '.db', '.db-wal', '.db-shm', '.db-journal') or suffix.startswith('.sqlite'):
        errors.append((name, 'forbidden file type'))
    if data.startswith(b'SQLite format 3\x00'):
        errors.append((name, 'SQLite database content'))
    if SECRET.search(data): errors.append((name, 'secret pattern'))
    if Path(name).name not in ('release-privacy-gate.py', 'publication-gate.sh') and PRIVATE.search(data):
        errors.append((name, 'site/workspace pattern'))
    if name.endswith(('.zip', '.whl')):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for entry in z.infolist():
                if not entry.is_dir(): scan(name+'!'+entry.filename, z.read(entry))
    elif name.endswith(('.tar.gz', '.tgz')):
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
            for entry in t:
                if entry.issym() or entry.islnk(): errors.append((name+'!'+entry.name, 'archive link'))
                elif entry.isfile(): scan(name+'!'+entry.name, t.extractfile(entry).read())

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', action='store_true')
parser.add_argument('assets', nargs='*')
args=parser.parse_args()
if args.source:
    for rel in subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z']).decode().split('\0'):
        if rel and Path(rel).is_file(): scan(rel, Path(rel).read_bytes())
for name in args.assets: scan(Path(name).name,Path(name).read_bytes())
for name, reason in errors: print('FAIL',reason,name)
print('RELEASE_PRIVACY_GATE', 'FAIL' if errors else 'PASS', 'files',count)
raise SystemExit(bool(errors))
