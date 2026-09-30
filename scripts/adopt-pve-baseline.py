#!/usr/bin/env python3
"""Operator-only, insert-only PVE baseline adoption from a pinned observation.

Not an Investigator/MCP capability. Caller supplies explicit resource scope,
user approval note, a fresh observation ID and a private backup directory.
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
    current = {}
    for item in json.loads(obs['payload_json']).get('resources', []):
        if item.get('type') in ('lxc', 'qemu'):
            identity = item['type'] + ':' + str(item.get('vmid'))
            if identity in current:
                raise ValueError('Duplicate observed resource identity')
            current[identity] = item
    rows = []
    for identity in resources:
        kind, key = identity.split(':', 1)
        if kind not in ('lxc', 'qemu') or not key.isascii() or not key.isdecimal():
            raise ValueError('Only explicit lxc/qemu numeric identities are allowed')
        item = current.get(identity)
        if item is None or item.get('status') not in ('running', 'stopped'):
            raise ValueError('Selected resource missing or status unknown: ' + identity)
        if conn.execute('SELECT 1 FROM resource_baseline WHERE resource_type=? AND resource_key=?', (kind, key)).fetchone():
            raise ValueError('Existing baseline must not be overwritten: ' + identity)
        rows.append({'resource_type':kind, 'resource_key':key, 'display_name':item.get('name'),
                     'expected_status':item['status'], 'baseline_state':'VERIFIED',
                     'source_observation':observation_id, 'note':note})
    return rows


def adopt(db, observation_id, resources, note, apply=False, backup_dir=None, now=None):
    if apply and backup_dir is None:
        raise ValueError('Apply requires a private backup directory')
    receipt = {'observation_id':observation_id, 'approval_note':note, 'state':'PLANNED'}
    with closing(sqlite3.connect('file:' + str(Path(db).resolve()) + ('?mode=rw' if apply else '?mode=ro'), uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        # Validate before creating a backup; revalidate within the write transaction.
        propose(conn, observation_id, resources, note, now)
        if apply:
            directory = Path(tempfile.mkdtemp(prefix='pve-baseline-', dir=backup_dir))
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
                    conn.execute('INSERT INTO resource_baseline(resource_type,resource_key,display_name,expected_status,baseline_state,source_observation,note) VALUES(:resource_type,:resource_key,:display_name,:expected_status,:baseline_state,:source_observation,:note)', row)
                receipt['after_count'] = conn.execute('SELECT COUNT(*) FROM resource_baseline').fetchone()[0]
                assert receipt['after_count'] == receipt['before_count'] + len(rows)
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True, type=Path)
    p.add_argument('--observation-id', required=True, type=int)
    p.add_argument('--resource', required=True, action='append')
    p.add_argument('--approval-note', required=True)
    p.add_argument('--backup-dir', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    if a.apply and os.geteuid() != 0:
        p.error('Apply is an operator action requiring root')
    print(json.dumps(adopt(a.db, a.observation_id, a.resource, a.approval_note,
                           a.apply, a.backup_dir), indent=2))


if __name__ == '__main__':
    main()
