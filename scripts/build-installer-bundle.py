#!/usr/bin/env python3
"""Build an offline installer with declared permissions, not checkout chmod state."""
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'scripts/bootstrap-wheel.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
EXECUTABLES = {'scripts/install.sh', 'scripts/uninstall.sh', 'scripts/bootstrap-wheel.py','scripts/lifecycle.py'}

def build(root=ROOT):
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    bootstrap.require(version == bootstrap.VERSION, 'bootstrap/candidate version differs')
    wheel = root / 'dist' / bootstrap.APP_NAME
    payloads = {name: bootstrap.trusted_read(wheel if name == bootstrap.APP_NAME else root / name, os.getuid()) for name in bootstrap.BUNDLE_FILES}
    bootstrap.require(bootstrap.digest(payloads['packaging/bootstrap/' + bootstrap.INSTALLER_NAME]) == bootstrap.INSTALLER_SHA256, 'bootstrap installer hash mismatch')
    bootstrap.validate_wheel(payloads['packaging/bootstrap/' + bootstrap.INSTALLER_NAME], 'installer', bootstrap.INSTALLER_VERSION)
    bootstrap.validate_wheel(payloads[bootstrap.APP_NAME], 'rackmarshal', version)
    payloads['install-manifest.json'] = (json.dumps({'version': version, 'source_commit': os.environ.get('RACKMARSHAL_BUILD_SOURCE'), 'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())}}, sort_keys=True, indent=2) + '\n').encode()
    epoch = int(os.environ['SOURCE_DATE_EPOCH'] if 'SOURCE_DATE_EPOCH' in os.environ else subprocess.check_output(['git', '-C', str(root), 'log', '-1', '--format=%ct'], text=True).strip())
    bootstrap.require(0 <= epoch <= 0xffffffff, 'invalid source epoch')
    label = 'rackmarshal-installer-' + version.replace('rc', '-rc')
    directories = {label}
    for name in payloads:
        directories.update(str(Path(label, name).parent) for _ in [0])
        directories.update(str(p) for p in Path(label, name).parents if str(p) != '.')
    output = root / 'dist' / (label + '.tar.gz')
    with output.open('xb') as stream, gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.GNU_FORMAT) as archive:
            entries = {name: None for name in directories}
            entries.update({label + '/' + name: data for name, data in payloads.items()})
            for name, data in sorted(entries.items()):
                info = tarfile.TarInfo(name)
                info.uid = info.gid = 0; info.uname = info.gname = ''; info.mtime = epoch
                info.mode = 0o755 if data is None or name.removeprefix(label + '/') in EXECUTABLES else 0o644
                info.type = tarfile.DIRTYPE if data is None else tarfile.REGTYPE
                if data is not None: info.size = len(data)
                archive.addfile(info, None if data is None else io.BytesIO(data))
    return output

if __name__ == '__main__':
    print(build())
