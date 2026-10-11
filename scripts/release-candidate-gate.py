#!/usr/bin/env python3
"""Verify exact candidate receipts and scan final assets before writing checksums."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib

REQUIRED = ('tests', 'lifecycle', 'privacy_review', 'dependency_review', 'synthetic_72h')
CLIENTS = {'local_explicit', 'private_hosted_explicit', 'desktop', 'implicit', 'other_clients', 'broader_distribution'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate evidence field')
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_object)


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None: raise ValueError('timestamp must have a timezone')
    return result.astimezone(timezone.utc)


def verify_window(receipt, kind):
    if receipt.get('kind') != kind: raise ValueError('wrong evidence scope')
    samples = receipt.get('samples', [])
    if len(samples) < 2: raise ValueError('missing window samples')
    times = []
    for index, sample in enumerate(samples):
        if sample.get('sequence') != index or sample.get('result') != 'PASS':
            raise ValueError('failed or discontinuous window')
        times.append(instant(sample['at']))
    if any(not 0 < (b-a).total_seconds() <= 420 for a,b in zip(times,times[1:])):
        raise ValueError('invalid sample gap')
    if (times[-1]-times[0]).total_seconds() < 72*3600 or times[-1] > datetime.now(timezone.utc):
        raise ValueError('window incomplete or in the future')
    if instant(receipt['start']) != times[0] or instant(receipt['finished']) != times[-1]:
        raise ValueError('window identity mismatch')


def verify(record, root, source, artifacts, scope):
    if not re.fullmatch(r'[0-9a-f]{40}', source) or record.get('source_commit') != source:
        raise ValueError('qualification source mismatch')
    if record.get('artifacts') != artifacts: raise ValueError('qualification artifact mismatch')
    supported = record.get('supported_activation', [])
    if not isinstance(supported, list) or len(set(supported)) != len(supported) or not {'local_explicit','private_hosted_explicit'} <= set(supported) or not set(supported) <= CLIENTS:
        raise ValueError('activation scope must be explicit')
    gates = record.get('gates', {})
    if 'production_routine_72h' not in gates: raise ValueError('production evidence state missing')
    required = set(REQUIRED) | {'activation_' + name for name in supported}
    if scope == 'stable': required.add('production_routine_72h')
    allowed = set(REQUIRED) | {'production_routine_72h'} | {'activation_' + name for name in CLIENTS}
    if not set(gates) <= allowed: raise ValueError('unknown evidence gate')
    for name in required:
        if gates.get(name, {}).get('status', 'PENDING') != 'PASS': raise ValueError('gate not passed: ' + name)
    # Validate every PASS claim, including optional scopes; do not accept an unsupported claim silently.
    for name, gate in gates.items():
        status = gate.get('status', 'PENDING')
        if status not in ('PENDING','FAIL','PASS','UNSUPPORTED'): raise ValueError('invalid evidence state')
        if status != 'PASS': continue
        if name.startswith('activation_') and name[len('activation_'):] not in supported:
            raise ValueError('activation PASS outside supported scope')
        path = (root / gate['receipt']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file(): raise ValueError('invalid receipt path')
        if digest(path) != gate.get('sha256'): raise ValueError('receipt hash mismatch: ' + name)
        receipt = read_json(path)
        if receipt.get('result') != 'PASS' or receipt.get('gate') != name or receipt.get('source_commit') != source or receipt.get('artifacts') != artifacts:
            raise ValueError('receipt identity/result mismatch: ' + name)
        if name == 'synthetic_72h': verify_window(receipt, 'disposable_synthetic')
        if name == 'production_routine_72h': verify_window(receipt, 'production_routine_use')
        if name.startswith('activation_') and receipt.get('activation') != name[len('activation_'):]:
            raise ValueError('activation receipt scope mismatch')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--source', required=True)
    parser.add_argument('--scope', choices=('candidate','stable'), default='candidate')
    args = parser.parse_args()
    try:
        actual = subprocess.check_output(['git','rev-parse','HEAD'],text=True,timeout=30).strip()
        if actual != args.source: raise ValueError('checkout/source mismatch')
        if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],text=True,timeout=30).strip():
            raise ValueError('tracked source edits are not qualified')
        version = tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
        if 'rc' not in version and args.scope != 'stable': raise ValueError('stable version requires routine-use evidence')
        label = version.replace('rc','-rc')
        expected = {f'rackmarshal-{version}-py3-none-any.whl', f'rackmarshal-{version}.tar.gz',
                    f'rackmarshal-installer-{label}.tar.gz', f'rackmarshal-investigator-{label}-local.zip'}
        files = list(args.dist.iterdir())
        if {p.name for p in files} != expected or any(not p.is_file() or p.is_symlink() for p in files):
            raise ValueError('unexpected or missing release assets')
        before = {p.name:digest(p) for p in files}
        verify(read_json(args.record), args.record.parent, actual, before, args.scope)
        subprocess.run([sys.executable,'scripts/release-privacy-gate.py', *map(str,sorted(files))],check=True)
        if before != {p.name:digest(p) for p in files}: raise ValueError('assets changed during scan')
        with Path('SHA256SUMS').open('x') as stream:
            for name in sorted(before): stream.write(before[name] + '  ' + name + '\n')
        print('RELEASE_CANDIDATE_GATE PASS')
        return 0
    except (ValueError, KeyError, TypeError, AttributeError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print('RELEASE_CANDIDATE_GATE FAIL: missing, invalid or mismatched evidence/assets', file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
