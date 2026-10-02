#!/usr/bin/env python3
"""Scan public source and recursively expanded release assets without extraction."""
import argparse
import io
import lzma
import re
import subprocess
import stat
import tarfile
import zipfile
import zlib
from pathlib import Path

PRIVATE = re.compile(rb"192\.168\.|\b10\.[0-9]+\.[0-9]+\.[0-9]+|\b172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+|\b(?:Michael|Olivia|Preston|ms01)\b|asdk_app_[a-z0-9]+|6abd[0-9a-f]{20,}|chatgpt\.com/c/|/root/rackmarshal|/var/lib/homelab|/data/family|homelab-backups|weekly-homelab", re.I)
SECRET = re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}")
EXCLUDED = ("internal/", "evals/results/", "packaging/chatgpt-business/")
errors = []
count = 0

def scan(member, data, label=None):
    """Keep the actual member path separate from its diagnostic archive label."""
    global count
    count += 1
    name = label if label is not None else member
    parts = Path(member).parts
    if any(x.startswith('..') for x in parts) or Path(member).is_absolute():
        errors.append((name, 'unsafe member path'))
    if any(x in parts for x in ('.git', 'chatgpt-business', 'internal')) or 'evals/results/' in member:
        errors.append((name, 'private path'))
    suffix = Path(member).suffix.lower()
    if suffix in ('.env', '.pem', '.key', '.db', '.db-wal', '.db-shm', '.db-journal') or suffix.startswith('.sqlite'):
        errors.append((name, 'forbidden file type'))
    if data.startswith(b'SQLite format 3\x00'):
        errors.append((name, 'SQLite database content'))
    if SECRET.search(data): errors.append((name, 'secret pattern'))
    is_zip = zipfile.is_zipfile(io.BytesIO(data))
    zip_expected = member.lower().endswith(('.zip', '.whl')) or data.startswith(b'PK\x03\x04')
    tar_expected = member.lower().endswith(('.tar.gz', '.tgz')) or data.startswith(b'\x1f\x8b')
    if Path(member).name not in ('release-privacy-gate.py', 'publication-gate.sh') and PRIVATE.search(data):
        errors.append((name, 'site/workspace pattern'))
    try:
        if is_zip or zip_expected:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for entry in z.infolist():
                    child_label = name + '!' + entry.filename
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        errors.append((child_label, 'archive link'))
                    elif not entry.is_dir():
                        scan(entry.filename, z.read(entry), child_label)
        elif tar_expected:
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
                for entry in t:
                    child_label = name + '!' + entry.name
                    if entry.issym() or entry.islnk(): errors.append((child_label, 'archive link'))
                    elif entry.isfile():
                        with t.extractfile(entry) as stream:
                            scan(entry.name, stream.read(), child_label)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, tarfile.TarError, EOFError, zlib.error, lzma.LZMAError):
        # Do not print exception bodies, member contents, or encryption details.
        errors.append((name, 'unreadable archive'))

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
