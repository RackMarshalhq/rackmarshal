#!/usr/bin/env python3
"""Operator-only, insert-only ZFS baseline adoption from a recorded observation.

Not an Investigator/MCP capability. The caller names the pools to adopt, gives
an approval note, and pins one fresh stored ZFS observation. Only a pool that
is ONLINE with an explicit permanent error count of zero, and whose vdevs are
ONLINE with integer error counters, can be adopted. Existing baselines are
never changed. Without --apply the tool only prints the plan.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def _int(value):
    return type(value) is int and value >= 0


def _flatten(pool_name, vdevs):
    result = {}

    def visit(vdev):
        if not isinstance(vdev, dict):
            raise ValueError('Pool %s contains an invalid vdev' % pool_name)
        name = vdev.get('name')
        if not isinstance(name, str) or not name:
            raise ValueError('Pool %s contains an unnamed vdev' % pool_name)
        if name in result:
            raise ValueError('Pool %s contains duplicate vdev %s' % (pool_name, name))
        result[name] = vdev
        children = vdev.get('children', [])
        if not isinstance(children, list):
            raise ValueError('Vdev %s/%s has invalid children' % (pool_name, name))
        for child in children:
            visit(child)

    if not isinstance(vdevs, list):
        raise ValueError('Pool %s has invalid vdevs' % pool_name)
    for vdev in vdevs:
        visit(vdev)
    return result


def propose(conn, observation_id, pools, note, now=None):
    if not note.strip() or not pools or len(pools) != len(set(pools)):
        raise ValueError('Require a nonempty approval note and unique pool scope')
    obs = conn.execute('SELECT * FROM zfs_observations WHERE id=?', (observation_id,)).fetchone()
    if obs is None:
        raise ValueError('Require a recorded ZFS observation')
    if obs['host_key_verified'] != 1:
        raise ValueError('Observation host key was not verified')
    observed = datetime.fromisoformat(obs['observed_at'].replace('Z', '+00:00'))
    if observed.tzinfo is None:
        raise ValueError('Observation timezone missing')
    age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
    if age < -60 or age > 900:
        raise ValueError('Observation must be fresh within 900 seconds')
    try:
        listed = json.loads(obs['payload_json']).get('pools')
    except json.JSONDecodeError:
        raise ValueError('Stored observation is not valid JSON')
    if not isinstance(listed, list):
        raise ValueError('Stored observation has invalid pools')
    current = {}
    for item in listed:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            raise ValueError('Stored observation contains an invalid pool')
        if item['name'] in current:
            raise ValueError('Duplicate observed pool: ' + item['name'])
        current[item['name']] = item
    pool_rows, vdev_rows = [], []
    for name in pools:
        item = current.get(name)
        if item is None:
            raise ValueError('Selected pool not in the observation: ' + name)
        guid = item.get('pool_guid')
        if not isinstance(guid, (str, int)) or isinstance(guid, bool) or not str(guid):
            raise ValueError('Pool %s has no usable pool_guid' % name)
        if item.get('state') != 'ONLINE':
            raise ValueError('Pool %s is not ONLINE; only a healthy pool can be adopted' % name)
        if not _int(item.get('error_count')) or item['error_count'] != 0:
            raise ValueError('Pool %s does not report zero permanent errors; refusing to adopt it' % name)
        if conn.execute('SELECT 1 FROM zfs_pool_baseline WHERE pool_name=? OR pool_guid=?', (name, str(guid))).fetchone():
            raise ValueError('Existing baseline must not be overwritten: ' + name)
        pool_rows.append({'pool_name': name, 'pool_guid': str(guid), 'baseline_state': 'VERIFIED',
                          'expected_state': 'ONLINE', 'expected_error_count': 0,
                          'source_observation_id': observation_id, 'note': note})
        for vname, vdev in _flatten(name, item.get('vdevs', [])).items():
            if not isinstance(vdev.get('type'), str) or not vdev['type']:
                raise ValueError('Vdev %s/%s has no type' % (name, vname))
            if vdev.get('state') != 'ONLINE':
                raise ValueError('Vdev %s/%s is not ONLINE; only a healthy pool can be adopted' % (name, vname))
            for field in ('read_errors', 'write_errors', 'checksum_errors'):
                if not _int(vdev.get(field)):
                    raise ValueError('Vdev %s/%s has no integer %s' % (name, vname, field))
            slow = vdev.get('slow_ios')
            if slow is not None and not _int(slow):
                raise ValueError('Vdev %s/%s has invalid slow_ios' % (name, vname))
            vdev_rows.append({'pool_name': name, 'vdev_name': vname, 'vdev_type': vdev['type'],
                              'baseline_state': 'VERIFIED', 'expected_state': 'ONLINE',
                              'expected_read_errors': vdev['read_errors'],
                              'expected_write_errors': vdev['write_errors'],
                              'expected_checksum_errors': vdev['checksum_errors'],
                              'expected_slow_ios': slow, 'path': vdev.get('path'),
                              'phys_path': vdev.get('phys_path'),
                              'source_observation_id': observation_id, 'note': note})
    return pool_rows, vdev_rows


def _counts(conn):
    return (conn.execute('SELECT COUNT(*) FROM zfs_pool_baseline').fetchone()[0],
            conn.execute('SELECT COUNT(*) FROM zfs_vdev_baseline').fetchone()[0])


def adopt(db, observation_id, pools, note, apply=False, backup_dir=None, now=None):
    if apply and backup_dir is None:
        raise ValueError('Apply requires a private backup directory')
    receipt = {'observation_id': observation_id, 'approval_note': note, 'state': 'PLANNED'}
    with closing(sqlite3.connect('file:' + str(Path(db).resolve()) + ('?mode=rw' if apply else '?mode=ro'), uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        # Validate before creating a backup; revalidate within the write transaction.
        propose(conn, observation_id, pools, note, now)
        if apply:
            directory = Path(tempfile.mkdtemp(prefix='zfs-baseline-', dir=backup_dir))
            directory.chmod(0o700)
            backup = directory / 'state-before.db'
            with closing(sqlite3.connect(backup)) as destination:
                conn.backup(destination)
            backup.chmod(0o600)
            receipt['backup'] = str(backup)
        try:
            conn.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
            pool_rows, vdev_rows = propose(conn, observation_id, pools, note, now)
            receipt['pool_rows'] = pool_rows
            receipt['vdev_rows'] = vdev_rows
            before = _counts(conn)
            receipt['before_count'] = {'pools': before[0], 'vdevs': before[1]}
            if apply:
                for row in pool_rows:
                    conn.execute('INSERT INTO zfs_pool_baseline(pool_name,pool_guid,baseline_state,expected_state,expected_error_count,source_observation_id,note) VALUES(:pool_name,:pool_guid,:baseline_state,:expected_state,:expected_error_count,:source_observation_id,:note)', row)
                for row in vdev_rows:
                    conn.execute('INSERT INTO zfs_vdev_baseline(pool_name,vdev_name,vdev_type,baseline_state,expected_state,expected_read_errors,expected_write_errors,expected_checksum_errors,expected_slow_ios,path,phys_path,source_observation_id,note) VALUES(:pool_name,:vdev_name,:vdev_type,:baseline_state,:expected_state,:expected_read_errors,:expected_write_errors,:expected_checksum_errors,:expected_slow_ios,:path,:phys_path,:source_observation_id,:note)', row)
                after = _counts(conn)
                receipt['after_count'] = {'pools': after[0], 'vdevs': after[1]}
                if after != (before[0] + len(pool_rows), before[1] + len(vdev_rows)):
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
    p.add_argument('--pool', required=True, action='append')
    p.add_argument('--approval-note', required=True)
    p.add_argument('--backup-dir', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    if a.apply and os.geteuid() != 0:
        p.error('Apply is an operator action requiring root')
    try:
        receipt = adopt(a.db, a.observation_id, a.pool, a.approval_note, a.apply, a.backup_dir)
    except ValueError as exc:
        raise SystemExit('REFUSED: %s' % exc)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
