#!/usr/bin/env python3
"""Operator-only retirement of PVE baseline rows for guests that no longer exist.

The mirror image of adopt-pve-baseline.py. When you delete a guest from Proxmox
its baseline row stays, and RackMarshal reports the guest as MISSING forever.
This tool removes the baseline row so the incident can close.

Safety rules:
* The caller names each guest (lxc:<id> or qemu:<id>), gives an approval note,
  a fresh PVE observation ID (less than 900 seconds old) and a private backup
  directory.
* Every named guest must be ABSENT from that observation. A guest that still
  exists is refused, so this cannot be used to switch off monitoring of a live
  guest.
* Every named guest must have a baseline row. Incidents, events and
  observations are never touched; they stay as history.
* Nothing is written without --apply, which needs root and first writes a copy
  of the database. One transaction; any failure rolls everything back.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def propose(conn, observation_id, resources, note, now=None):
    if not note.strip() or not resources or len(resources) != len(set(resources)):
        raise ValueError('Require a nonempty approval note and unique resource scope')
    obs = conn.execute('SELECT * FROM observations WHERE id=?', (observation_id,)).fetchone()
    if obs is None or obs['collector'] != 'pve_cluster_resources':
        raise ValueError('Require a recorded PVE observation')
    observed = datetime.fromisoformat(obs['observed_at'].replace('Z', '+00:00'))
    if observed.tzinfo is None:
        raise ValueError('Observation timezone missing')
    age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
    if age < -60 or age > 900:
        raise ValueError('Observation must be fresh within 900 seconds')
    if not obs['tls_verified']:
        raise ValueError('Observation must have verified TLS')
    present = set()
    for item in json.loads(obs['payload_json']).get('resources', []):
        if item.get('type') in ('lxc', 'qemu'):
            present.add(item['type'] + ':' + str(item.get('vmid')))
    rows = []
    for identity in resources:
        kind, _, key = identity.partition(':')
        if kind not in ('lxc', 'qemu') or not key.isascii() or not key.isdecimal():
            raise ValueError('Only explicit lxc/qemu numeric identities are allowed')
        if identity in present:
            raise ValueError('Guest still exists in the observation, refusing to retire: ' + identity)
        row = conn.execute('SELECT id, resource_type, resource_key, display_name, expected_status '
                           'FROM resource_baseline WHERE resource_type=? AND resource_key=?',
                           (kind, key)).fetchone()
        if row is None:
            raise ValueError('No baseline row to retire: ' + identity)
        rows.append({'id': row['id'], 'resource_type': kind, 'resource_key': key,
                     'display_name': row['display_name'], 'expected_status': row['expected_status']})
    return rows


def retire(db, observation_id, resources, note, apply=False, backup_dir=None, now=None):
    if apply and backup_dir is None:
        raise ValueError('Apply requires a private backup directory')
    receipt = {'observation_id': observation_id, 'approval_note': note, 'state': 'PLANNED'}
    with closing(sqlite3.connect('file:' + str(Path(db).resolve()) + ('?mode=rw' if apply else '?mode=ro'),
                                 uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        propose(conn, observation_id, resources, note, now)
        if apply:
            directory = Path(tempfile.mkdtemp(prefix='pve-baseline-retire-', dir=backup_dir))
            directory.chmod(0o700)
            backup = directory / 'state-before.db'
            with closing(sqlite3.connect(backup)) as destination:
                conn.backup(destination)
            backup.chmod(0o600)
            receipt['backup'] = str(backup)
        try:
            conn.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
            rows = propose(conn, observation_id, resources, note, now)
            receipt['rows'] = rows
            receipt['before_count'] = conn.execute('SELECT COUNT(*) FROM resource_baseline').fetchone()[0]
            if apply:
                for row in rows:
                    deleted = conn.execute('DELETE FROM resource_baseline WHERE id=? AND resource_type=? AND resource_key=?',
                                           (row['id'], row['resource_type'], row['resource_key'])).rowcount
                    if deleted != 1:
                        raise RuntimeError('Baseline row not deleted as expected; retirement rolled back')
                receipt['after_count'] = conn.execute('SELECT COUNT(*) FROM resource_baseline').fetchone()[0]
                if receipt['after_count'] != receipt['before_count'] - len(rows):
                    raise RuntimeError('Baseline row count changed unexpectedly; retirement rolled back')
                conn.commit()
                receipt['state'] = 'APPLIED'
            else:
                conn.rollback()
        except Exception:
            conn.rollback()
            raise
    if apply:
        (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', required=True, type=Path)
    p.add_argument('--observation-id', required=True, type=int)
    p.add_argument('--resource', required=True, action='append', help='lxc:<id> or qemu:<id>; repeat for each guest')
    p.add_argument('--approval-note', required=True)
    p.add_argument('--backup-dir', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    if a.apply and os.geteuid() != 0:
        p.error('Apply is an operator action requiring root')
    print(json.dumps(retire(a.db, a.observation_id, a.resource, a.approval_note,
                            a.apply, a.backup_dir), indent=2))


if __name__ == '__main__':
    main()
