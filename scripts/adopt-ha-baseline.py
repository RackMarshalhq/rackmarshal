#!/usr/bin/env python3
"""Operator-only, insert-only Home Assistant baseline adoption from a recorded observation.

Not an Investigator/MCP capability. The caller names the resources to adopt,
gives an approval note, and pins one fresh stored Home Assistant observation.
A resource is adopted only when its observed status equals the expected status
the collector itself declares for it. Existing baselines are never changed.
Without --apply the tool only prints the plan.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile

COLLECTOR = 'home_assistant'


def _text(value):
    return isinstance(value, str) and value != ''


def propose(conn, observation_id, resources, note, now=None):
    if not note.strip() or not resources or len(resources) != len(set(resources)):
        raise ValueError('Require a nonempty approval note and unique resource scope')
    obs = conn.execute('SELECT * FROM observations WHERE id=?', (observation_id,)).fetchone()
    if obs is None or obs['collector'] != COLLECTOR:
        raise ValueError('Require a recorded Home Assistant observation')
    if obs['tls_verified'] != 1:
        raise ValueError('Observation TLS was not verified')
    observed = datetime.fromisoformat(obs['observed_at'].replace('Z', '+00:00'))
    if observed.tzinfo is None:
        raise ValueError('Observation timezone missing')
    age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
    if age < -60 or age > 900:
        raise ValueError('Observation must be fresh within 900 seconds')
    try:
        listed = json.loads(obs['payload_json']).get('resources')
    except json.JSONDecodeError:
        raise ValueError('Stored observation is not valid JSON')
    if not isinstance(listed, list):
        raise ValueError('Stored observation has invalid resources')
    current = {}
    for item in listed:
        if not isinstance(item, dict) or not _text(item.get('resource_key')):
            raise ValueError('Stored observation contains an invalid resource')
        if item['resource_key'] in current:
            raise ValueError('Duplicate observed resource: ' + item['resource_key'])
        current[item['resource_key']] = item
    rows = []
    for key in resources:
        item = current.get(key)
        if item is None:
            raise ValueError('Selected resource not in the observation: ' + key)
        for field in ('resource_type', 'display_name', 'status', 'expected_status'):
            if not _text(item.get(field)):
                raise ValueError('Resource %s has no %s' % (key, field))
        if item['status'] != item['expected_status']:
            raise ValueError('Resource %s reports %s, not the expected %s; refusing to adopt it' % (key, item['status'], item['expected_status']))
        if conn.execute('SELECT 1 FROM ha_resource_baseline WHERE resource_key=?', (key,)).fetchone():
            raise ValueError('Existing baseline must not be overwritten: ' + key)
        rows.append({'resource_key': key, 'resource_type': item['resource_type'],
                     'display_name': item['display_name'], 'baseline_state': 'VERIFIED',
                     'expected_status': item['expected_status'],
                     'source_observation_id': observation_id, 'note': note})
    return rows


def adopt(db, observation_id, resources, note, apply=False, backup_dir=None, now=None):
    if apply and backup_dir is None:
        raise ValueError('Apply requires a private backup directory')
    receipt = {'observation_id': observation_id, 'approval_note': note, 'state': 'PLANNED'}
    with closing(sqlite3.connect('file:' + str(Path(db).resolve()) + ('?mode=rw' if apply else '?mode=ro'), uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        # Validate before creating a backup; revalidate within the write transaction.
        propose(conn, observation_id, resources, note, now)
        if apply:
            directory = Path(tempfile.mkdtemp(prefix='ha-baseline-', dir=backup_dir))
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
            receipt['before_count'] = conn.execute('SELECT COUNT(*) FROM ha_resource_baseline').fetchone()[0]
            if apply:
                for row in rows:
                    conn.execute('INSERT INTO ha_resource_baseline(resource_key,resource_type,display_name,baseline_state,expected_status,source_observation_id,note) VALUES(:resource_key,:resource_type,:display_name,:baseline_state,:expected_status,:source_observation_id,:note)', row)
                receipt['after_count'] = conn.execute('SELECT COUNT(*) FROM ha_resource_baseline').fetchone()[0]
                if receipt['after_count'] != receipt['before_count'] + len(rows):
                    raise RuntimeError('Baseline row count changed unexpectedly; adoption rolled back')
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
    try:
        receipt = adopt(a.db, a.observation_id, a.resource, a.approval_note, a.apply, a.backup_dir)
    except ValueError as exc:
        raise SystemExit('REFUSED: %s' % exc)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
