#!/usr/bin/env python3
"""Pinned offline fresh-venv bootstrap. Only Python's standard library is trusted initially."""
import argparse
import base64
import csv
import email.parser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile

VERSION = '1.3.0rc1'
INSTALLER_VERSION = '1.1.0'
INSTALLER_NAME = 'installer-1.1.0-py3-none-any.whl'
INSTALLER_SHA256 = 'f55f5728ff61d3dd54dbc5a397cf3f7307cb64b180c20b72afbebf01c9e2c8a0'
APP_NAME = 'rackmarshal-' + VERSION + '-py3-none-any.whl'
LIMIT = 32 * 1024 * 1024
DOCS = ('LICENSE', 'README.md', 'INSTALL.md', 'CONFIGURATION.md', 'UPGRADE.md', 'UNINSTALL.md', 'SECURITY.md', 'CHANGELOG.md', 'THIRD-PARTY-NOTICES.txt')
UNITS = ('rackmarshal-status.service', 'rackmarshal-notify.service', 'rackmarshal-notify.timer', 'rackmarshal-db-snapshot.service', 'rackmarshal-db-snapshot.timer', 'rackmarshal-domain@.service', 'rackmarshal-domain@.timer', 'rackmarshal-domain@.service.d/20-cycle-health.conf', 'rackmarshal-self-watch.service.d/20-cycle-health.conf')
TOOLS = ('scripts/adopt-pve-baseline.py', 'scripts/adopt-zfs-baseline.py', 'scripts/adopt-ha-baseline.py')
LIFECYCLE_FILES = {'scripts/lifecycle.py','rackmarshal/__init__.py','rackmarshal/maintenance/__init__.py'} | {'rackmarshal/maintenance/'+n+'.py' for n in ('lifecycle','lifecycle_systemd','lifecycle_semantics')}
BUNDLE_FILES = LIFECYCLE_FILES | set(DOCS) | set(TOOLS) | {'scripts/install.sh', 'scripts/uninstall.sh', 'scripts/bootstrap-wheel.py', 'packaging/bootstrap/manifest.json', 'packaging/bootstrap/' + INSTALLER_NAME, APP_NAME, 'config/rackmarshal.conf.example', 'config/mounts.catalog.example.toml'} | {'packaging/systemd/' + n for n in UNITS}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate manifest field')
        value[key] = item
    return value

def trusted_read(path, owner=0):
    """Reject writable/link inputs, including linked ancestors; read exactly one fd."""
    path = Path(path).absolute()
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), 'unsafe input ancestor: %s' % parent)
        # The input itself must be in owner-controlled storage. A sticky system
        # temporary ancestor may contain private fixtures/staging, but not files
        # directly supplied from that shared directory.
        require(info.st_uid in (0, owner), 'foreign input ancestor: %s' % parent)
        if info.st_mode & 0o022:
            require(info.st_uid == 0 and info.st_mode & stat.S_ISVTX and parent != path.parent, 'writable input ancestor: %s (reading %s)' % (parent, path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == owner and not info.st_mode & 0o022, 'unsafe input file')
        require(info.st_size <= LIMIT, 'oversized input')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(LIMIT + 1)
        require(len(data) == info.st_size, 'input changed while reading')
        return data
    finally:
        os.close(fd)

def validate_wheel(data, project, version):
    require(len(data) <= LIMIT, 'oversized wheel')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        require(0 < len(entries) <= 5000, 'wheel member count')
        seen, total, payloads = set(), 0, {}
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            require(name and not path.is_absolute() and '\\' not in name and not any(ord(c) < 32 or ord(c) == 127 for c in name), 'unsafe wheel name')
            require(all(p not in ('', '.', '..') for p in name.rstrip('/').split('/')), 'unsafe wheel path')
            canonical = name.rstrip('/')
            require(canonical not in seen, 'duplicate wheel entry')
            seen.add(canonical)
            mode = entry.external_attr >> 16
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR) and not entry.flag_bits & 1, 'special/encrypted wheel entry')
            require(stat.S_IFMT(mode) != stat.S_IFDIR or entry.is_dir(), 'wheel directory type mismatch')
            require(stat.S_IFMT(mode) != stat.S_IFREG or not entry.is_dir(), 'wheel file type mismatch')
            require(entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'unsupported wheel compression')
            require(path.parts[0] in (project, project + '-' + version + '.dist-info'), 'unexpected wheel root')
            require(path.suffix != '.pth' and path.name not in ('sitecustomize.py', 'usercustomize.py'), 'Python startup hook in wheel')
            total += entry.file_size
            require(0 <= entry.file_size <= LIMIT and total <= LIMIT, 'wheel expansion limit')
            if not entry.is_dir():
                with archive.open(entry) as stream:
                    payload = stream.read(LIMIT + 1)
                require(len(payload) == entry.file_size, 'wheel size mismatch')
                payloads[name] = payload
        for name in seen:
            for parent in PurePosixPath(name).parents:
                require(str(parent) not in payloads, 'wheel path conflict')
        meta = email.parser.BytesParser().parsebytes(payloads[project + '-' + version + '.dist-info/METADATA'])
        require(meta.get_all('Name') == [project] and meta.get_all('Version') == [version], 'wrong wheel identity')
        record_name = project + '-' + version + '.dist-info/RECORD'
        records = set()
        for row in csv.reader(io.StringIO(payloads[record_name].decode('utf-8'))):
            require(len(row) == 3 and row[0] not in records, 'invalid wheel RECORD')
            name, checksum, size = row
            records.add(name)
            require(name in payloads, 'wheel RECORD has unknown member')
            if name == record_name:
                require(checksum == size == '', 'invalid wheel RECORD self entry')
            else:
                actual = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(payloads[name]).digest()).decode().rstrip('=')
                require(checksum == actual and size == str(len(payloads[name])), 'wheel RECORD mismatch')
        require(records == set(payloads), 'wheel RECORD omits member')
        return payloads

def assert_fresh_paths(paths, owner=0):
    for raw in paths:
        path = Path(raw).absolute()
        require(not os.path.lexists(path), 'existing installation path; preserve and review')
        for parent in path.parents:
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), 'unsafe installation ancestor: %s' % parent)
            require(info.st_uid in (0, owner) and not info.st_mode & 0o022, 'writable/foreign installation ancestor: %s' % parent)

def prepare(bundle, wheel, staging_parent='/run', owner=0, config=None):
    """Validate all inputs before creating private staging or persistent install paths."""
    bundle = Path(bundle).absolute()
    manifest = json.loads(trusted_read(bundle / 'install-manifest.json', owner), object_pairs_hook=unique_object)
    require(manifest.get('version') == VERSION and set(manifest.get('files', {})) == BUNDLE_FILES, 'incomplete install manifest')
    payloads = {}
    for name, expected in manifest['files'].items():
        require(isinstance(expected, str) and len(expected) == 64, 'invalid input hash')
        data = trusted_read(wheel if name == APP_NAME else bundle / name, owner)
        require(digest(data) == expected, 'bundle input hash mismatch: ' + name)
        payloads[name] = data
    require(Path(wheel).name == APP_NAME, 'unexpected application wheel basename')
    require(digest(payloads['packaging/bootstrap/' + INSTALLER_NAME]) == INSTALLER_SHA256, 'untrusted installer wheel')
    validate_wheel(payloads['packaging/bootstrap/' + INSTALLER_NAME], 'installer', INSTALLER_VERSION)
    validate_wheel(payloads[APP_NAME], 'rackmarshal', VERSION)
    config_data = trusted_read(config, owner) if config is not None else None
    info = Path(staging_parent).lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner and not info.st_mode & 0o022, 'unsafe staging parent')
    stage = Path(tempfile.mkdtemp(prefix='rackmarshal-install-', dir=staging_parent))
    stage.chmod(0o700)
    for name, data in payloads.items():
        path = stage / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open('xb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        require(digest(path.read_bytes()) == manifest['files'][name], 'staging readback mismatch')
    (stage / 'install-manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
    (stage / 'install-manifest.json').chmod(0o600)
    if config_data is not None:
        with (stage / 'supplied.conf').open('xb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(config_data)
    return stage

RUNNER = r'''
import hashlib, json, pathlib, runpy, sys
wheel, expected, target, app, app_hash, final_python = json.loads(sys.argv[1])
if pathlib.Path(sys.prefix) != pathlib.Path(target) or sys.prefix == sys.base_prefix:
    raise RuntimeError('wrong bootstrap target')
if hashlib.sha256(pathlib.Path(wheel).read_bytes()).hexdigest() != expected:
    raise RuntimeError('installer changed')
if hashlib.sha256(pathlib.Path(app).read_bytes()).hexdigest() != app_hash:
    raise RuntimeError('application changed')
def offline(event, arguments):
    if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname'):
        raise RuntimeError('network prohibited during offline bootstrap')
sys.addaudithook(offline)
sys.path.insert(0, wheel)
import installer
if installer.__version__ != '1.1.0' or installer.__file__ != wheel + '/installer/__init__.py':
    raise RuntimeError('unexpected installer import')
if final_python:
    from installer.__main__ import _get_scheme_dict, get_launcher_kind
    from installer.destinations import SchemeDictionaryDestination
    from installer.sources import WheelFile
    with WheelFile.open(app) as source:
        source.validate_record(validate_contents=True)
        destination=SchemeDictionaryDestination(scheme_dict=_get_scheme_dict(source.distribution,prefix=None),interpreter=final_python,script_kind=get_launcher_kind(),bytecode_optimization_levels=[])
        installer.install(source,destination,{})
else:
    sys.argv = ['installer', '--validate-record', 'all', '--no-compile-bytecode', app]
    runpy.run_module('installer', run_name='__main__')
'''

def validate_target(target, owner=0):
    target = Path(target).absolute()
    require(target.is_dir() and not target.is_symlink(), 'target must be a new real venv')
    for path in [target, *target.rglob('*')]:
        info = path.lstat()
        require(info.st_uid == owner, 'foreign venv entry')
        if path.is_symlink():
            require((path.parent == target / 'bin' and path.name in ('python', 'python3', 'python' + str(sys.version_info.major) + '.' + str(sys.version_info.minor))) or (path.name == 'lib64' and path.parent == target and os.readlink(path) == 'lib'), 'unexpected venv link')
            if path.parent == target / 'bin':
                require(path.resolve() == Path(sys.executable).resolve(), 'unexpected interpreter link')
        else:
            require(not info.st_mode & 0o022 and (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)), 'unsafe venv entry %s mode %o' % (path, info.st_mode))
            require(not stat.S_ISREG(info.st_mode) or info.st_nlink == 1, 'hard-linked venv entry')
        require(path.suffix != '.pth' and path.name not in ('sitecustomize.py', 'usercustomize.py'), 'venv startup hook')
    cfg = (target / 'pyvenv.cfg').read_text()
    require('include-system-site-packages = false' in cfg.splitlines(), 'system site packages must be disabled')
    require((target / 'bin/python').resolve() == Path(sys.executable).resolve(), 'unexpected venv interpreter')
    return target

def verify_inventory(target, distributions, owner=0):
    sites = list(target.glob('lib/python*/site-packages'))
    require(len(sites) == 1, 'unexpected site-packages layout')
    site = sites[0]
    expected = set()
    for project, version, payloads in distributions:
        prefix = project + '-' + version + '.dist-info/'
        expected.update(payloads)
        record = site / (prefix + 'RECORD')
        recorded = set()
        for row in csv.reader(io.StringIO(trusted_read(record, owner).decode())):
            require(len(row) == 3 and row[0] not in recorded, 'invalid installed RECORD')
            name, checksum, size = row
            recorded.add(name)
            path = (site / name).resolve()
            require(path.is_relative_to(target.resolve()), 'installed RECORD escapes venv')
            data = trusted_read(path, owner)
            if path == record.resolve():
                require(checksum == size == '', 'invalid RECORD self entry')
            else:
                actual = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
                require(checksum == actual and size == str(len(data)), 'installed RECORD mismatch')
        require(set(payloads).issubset(recorded), 'installed RECORD omits payload')
    actual = {str(p.relative_to(site)) for p in site.rglob('*') if p.is_file()}
    require(actual == expected, 'unexpected or missing installed files')

def install(stage, target, owner=0, final_python=None):
    stage, target = Path(stage).absolute(), validate_target(target, owner)
    require(final_python is None or final_python == '/opt/rackmarshal/venv/bin/python', 'unsupported final interpreter')
    info = stage.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner and stat.S_IMODE(info.st_mode) == 0o700, 'unsafe staging directory')
    manifest = json.loads(trusted_read(stage / 'install-manifest.json', owner), object_pairs_hook=unique_object)
    require(manifest.get('version') == VERSION and set(manifest.get('files', {})) == BUNDLE_FILES, 'invalid staged manifest')
    installer_wheel = stage / 'packaging/bootstrap' / INSTALLER_NAME
    installer_data = trusted_read(installer_wheel, owner)
    require(digest(installer_data) == INSTALLER_SHA256, 'staged installer changed')
    validate_wheel(installer_data, 'installer', INSTALLER_VERSION)
    app_wheel = stage / APP_NAME
    app_data = trusted_read(app_wheel, owner)
    require(digest(app_data) == manifest['files'][APP_NAME], 'staged application changed')
    payloads = validate_wheel(app_data, 'rackmarshal', VERSION)
    # No pre-existing code may run at Python startup or be silently repaired.
    require(not any(target.glob('lib/python*/site-packages/*')), 'target is not pipless/empty')
    receipt = {'result': 'IN_PROGRESS', 'installer_sha256': INSTALLER_SHA256, 'application_sha256': digest(app_data), 'target': str(target), 'commands': []}
    receipt_path = stage / 'bootstrap-receipt.json'
    with receipt_path.open('x') as stream:
        stream.write(json.dumps(receipt) + '\n')
    env = {'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1', 'LC_ALL': 'C'}
    try:
        spec = json.dumps([str(installer_wheel), INSTALLER_SHA256, str(target), str(app_wheel), digest(app_data), final_python])
        result = subprocess.run([str(target / 'bin/python'), '-I', '-B', '-c', RUNNER, spec], cwd=stage, env=env, capture_output=True, text=True, timeout=120)
        receipt['commands'].append({'project': 'rackmarshal', 'arguments': ['--validate-record', 'all', '--no-compile-bytecode', str(app_wheel)], 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        require(result.returncode == 0, 'offline installation failed')
        sites = list(target.glob('lib/python*/site-packages'))
        require(len(sites) == 1, 'unexpected site-packages layout')
        for name, data in payloads.items():
            if name.endswith('.dist-info/RECORD'):
                continue  # installer records generated console scripts.
            require(trusted_read(sites[0] / name, owner) == data, 'installed payload differs: ' + name)
        require((sites[0] / 'rackmarshal/__init__.py').is_file(), 'installed package absent')
        verify_inventory(target, [('rackmarshal', VERSION, payloads)], owner)
        validate_target(target, owner)
        receipt['result'] = 'PASS'
    except Exception as exc:
        receipt['result'], receipt['error'] = 'FAIL', str(exc)
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--bundle', required=True); prep.add_argument('--wheel', required=True); prep.add_argument('--config')
    run = sub.add_parser('install'); run.add_argument('--stage', required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0 and sys.version_info >= (3, 11), 'root and Python >=3.11 required')
    if args.action == 'prepare':
        assert_fresh_paths(('/opt/rackmarshal', '/etc/rackmarshal', '/var/lib/rackmarshal', '/var/log/rackmarshal'))
        print(prepare(args.bundle, args.wheel, config=args.config))
    else:
        stage = Path(args.stage)
        require(stage.parent == Path('/run') and stage.name.startswith('rackmarshal-install-'), 'unexpected stage path')
        install(stage, '/opt/rackmarshal/venv')
        print('OFFLINE_BOOTSTRAP_PASS')

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print('STOP: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
