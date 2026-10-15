#!/usr/bin/env python3
"""Scan public source and recursively expanded release assets without extraction."""
import argparse
import io
import bz2
import gzip
import hashlib
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
expanded_bytes = 0
budget_exhausted = False

class ScanLimit(ValueError):
    def __init__(self, message):
        global budget_exhausted
        budget_exhausted = True
        super().__init__(message)

MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10000
MAX_DEPTH = 12
# Exempt only exact reviewed declaration lines at their source paths.
PATTERN_LINES = {'scripts/release-privacy-gate.py': '884ddf5ffc25652b3d14579ec063969009266a7248bbf528449e2fd5718b3016', 'scripts/publication-gate.sh': '1e36a382407eba1652a384f908bf7e6afdbde88588630ce1075323c6aeb08d38'}

def bounded_read(stream):
    if budget_exhausted: raise ScanLimit('scan budget exhausted')
    remaining = min(MAX_MEMBER_BYTES, MAX_TOTAL_BYTES - expanded_bytes)
    if remaining <= 0 or count >= MAX_MEMBERS: raise ScanLimit('scan resource limit')
    data = stream.read(remaining + 1)
    if len(data) > remaining: raise ScanLimit('scan resource limit')
    return data


PUBLIC_SITE_PAGES = frozenset(('site/about.html', 'site/docs.html', 'site/index.html', 'site/install.html'))

def archive_root(names):
    """Recognize one safe source-archive wrapper, anchored by project metadata."""
    paths = [Path(name) for name in names]
    if not paths or any(path.is_absolute() or not path.parts or
                        any(part.startswith('..') for part in path.parts) for path in paths):
        return None
    roots = {path.parts[0] for path in paths}
    if len(roots) != 1:
        return None
    root = roots.pop()
    if root in ('.git', 'internal', 'chatgpt-business'):
        return None
    return root if root + '/pyproject.toml' in names else None

def scan(member, data, label=None, root=None, depth=0):
    """Keep the actual member path separate from its diagnostic archive label."""
    global count, expanded_bytes
    count += 1
    name = label if label is not None else member
    expanded_bytes += len(data)
    if depth > MAX_DEPTH or count > MAX_MEMBERS or len(data) > MAX_MEMBER_BYTES or expanded_bytes > MAX_TOTAL_BYTES:
        raise ScanLimit('scan resource limit')
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
    lower = member.lower()
    compression = ('gz' if data.startswith(b'\x1f\x8b') else
                   'bz2' if data.startswith(b'BZh') else
                   'xz' if data.startswith(b'\xfd7zXZ\x00') else None)
    expected_compression = ('gz' if lower.endswith(('.gz', '.tgz')) else
                            'bz2' if lower.endswith(('.bz2', '.tbz', '.tbz2')) else
                            'xz' if lower.endswith(('.xz', '.txz')) else None)
    tar_expected = lower.endswith('.tar') or data[257:262] == b'ustar'
    container = is_zip or zip_expected or compression or expected_compression or tar_expected
    public_member = member
    if root and member.startswith(root + '/'):
        public_member = member[len(root) + 1:]
    public_data = data
    if public_member in PUBLIC_SITE_PAGES:
        public_data = public_data.replace(b'Mi' + b'chael Poteet', b'').replace(b'mi' + b'chael@rackmarshal.com', b'')
    approved = {PATTERN_LINES.get(public_member)}
    if container:
        # Inspect retained archive bytes (comments, prefixes, trailers, metadata)
        # as well as expanded members. Member checks enforce the path scope.
        approved = set(PATTERN_LINES.values())
        public_data = public_data.replace(b'Mi' + b'chael Poteet', b'').replace(b'mi' + b'chael@rackmarshal.com', b'')
    public_data = b'\n'.join(line for line in public_data.splitlines()
                              if hashlib.sha256(line).hexdigest() not in approved)
    if PRIVATE.search(public_data): errors.append((name, 'site/workspace pattern'))
    try:
        if container and depth >= MAX_DEPTH: raise ScanLimit('scan depth limit')
        if is_zip or zip_expected:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                entries = z.infolist()
                if len(entries) > MAX_MEMBERS - count: raise ScanLimit('member count')
                child_root = archive_root([entry.filename for entry in entries])
                for entry in entries:
                    child_label = name + '!' + entry.filename
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        errors.append((child_label, 'archive link'))
                    elif not entry.is_dir():
                        if entry.file_size > MAX_MEMBER_BYTES: raise ScanLimit('member size')
                        # zipfile exposes no LZMA decoder memory limit; fail closed.
                        if entry.compress_type == zipfile.ZIP_LZMA: raise ValueError('unsupported ZIP compression')
                        with z.open(entry) as stream:
                            scan(entry.filename, bounded_read(stream), child_label, child_root, depth + 1)
        elif compression or expected_compression:
            if expected_compression and compression != expected_compression: raise ValueError('compression mismatch')
            if compression == 'xz':
                # Bound both output and the XZ dictionary allocation. A plain
                # LZMAFile output limit alone would not bound decoder memory.
                remaining = min(MAX_MEMBER_BYTES, MAX_TOTAL_BYTES - expanded_bytes)
                if budget_exhausted or remaining <= 0: raise ScanLimit('scan resource limit')
                decoder = lzma.LZMADecompressor(memlimit=MAX_MEMBER_BYTES)
                expanded = decoder.decompress(data, max_length=remaining + 1)
                if len(expanded) > remaining: raise ScanLimit('scan resource limit')
                if not decoder.eof or decoder.unused_data: raise ValueError('incomplete or trailing XZ stream')
            else:
                opener = {'gz': gzip.open, 'bz2': bz2.BZ2File}[compression]
                with opener(io.BytesIO(data), mode='rb') as stream: expanded = bounded_read(stream)
            child = member.rsplit('.', 1)[0] if '.' in member else member + '.expanded'
            if lower.endswith(('.tgz', '.tbz', '.tbz2', '.txz')): child += '.tar'
            scan(child, expanded, name + '!expanded', root, depth + 1)
        elif tar_expected:
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as t:
                entries = []
                for entry in t:
                    entries.append(entry)
                    if len(entries) > MAX_MEMBERS - count: raise ScanLimit('member count')
                child_root = archive_root([entry.name for entry in entries])
                for entry in entries:
                    child_label = name + '!' + entry.name
                    if entry.issym() or entry.islnk(): errors.append((child_label, 'archive link'))
                    elif not entry.isdir() and not entry.isfile(): errors.append((child_label, 'archive special file'))
                    elif entry.isfile():
                        with t.extractfile(entry) as stream:
                            scan(entry.name, bounded_read(stream), child_label, child_root, depth + 1)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, tarfile.TarError, EOFError, zlib.error, lzma.LZMAError):
        # Do not print exception bodies, member contents, or encryption details.
        errors.append((name, 'unreadable archive'))

def scan_path(member, path):
    try:
        with path.open('rb') as stream: scan(member, bounded_read(stream))
    except (OSError, ValueError): errors.append((member, 'unreadable or oversized file'))

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', action='store_true')
parser.add_argument('assets', nargs='*')
args=parser.parse_args()
if args.source:
    for rel in subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'], timeout=30).decode().split('\0'):
        if rel and Path(rel).is_file(): scan_path(rel, Path(rel))
for name in args.assets: scan_path(Path(name).name, Path(name))
for name, reason in errors: print('FAIL',reason,name)
print('RELEASE_PRIVACY_GATE', 'FAIL' if errors else 'PASS', 'files',count)
raise SystemExit(bool(errors))
