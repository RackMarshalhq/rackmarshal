#!/usr/bin/env python3
"""Operator-only, insert-only one-time copy of baselines from an older RackMarshal database.

For moving an existing 1.0.0 site to a fresh 1.3 installation whose database
is still empty. Copies the baseline tables (PVE, Home Assistant, backup, ZFS)
and only the observation rows those baselines cite, with their original ids.
History, events and incidents are NOT copied. Not part of the installer bundle.
The old database is opened read-only; use a copy or a database snapshot.
Without --apply the tool only prints the plan.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile

# (table, source-observation column, observation table); parents before children.
BASELINES = (
    ('resource_baseline', 'source_observation', 'observations'),
    ('ha_resource_baseline', 'source_observation_id', 'observations'),
    ('backup_job_baseline', 'source_observation_id', 'observations'),
    ('backup_guest_baseline', 'source_observation_id', 'observations'),
    ('zfs_pool_baseline', 'source_observation_id', 'zfs_observations'),
    ('zfs_vdev_baseline', 'source_observation_id', 'zfs_observations'),
)
OBSERVATION_TABLES = ('observations', 'zfs_observations')


def _schema(conn, schema, table):
    row = conn.execute('SELECT sql FROM %s.sqlite_master WHERE type=? AND name=?' % schema, ('table', table)).fetchone()
    return None if row is None else ' '.join(row[0].split())


def _count(conn, schema, table):
    return conn.execute('SELECT COUNT(*) FROM %s.%s' % (schema, table)).fetchone()[0]


def check(conn):
    """Raise ValueError unless the new database is fresh and the schemas match."""
    query = 'SELECT id, checksum FROM %s.schema_migrations ORDER BY id'
    if conn.execute(query % 'old').fetchall() != conn.execute(query % 'main').fetchall():
        raise ValueError('The two databases are at different schema versions; refusing to copy')
    for table in [b[0] for b in BASELINES] + list(OBSERVATION_TABLES):
        if _schema(conn, 'old', table) != _schema(conn, 'main', table):
            raise ValueError('Table %s differs between the two databases; refusing to copy' % table)
        if _count(conn, 'main', table):
            raise ValueError('The new database already has rows in %s; this tool needs a fresh database' % table)


def plan(conn):
    steps, warnings = [], []
    ids = {name: set() for name in OBSERVATION_TABLES}
    for table, column, obs in BASELINES:
        rows = conn.execute('SELECT %s FROM old.%s' % (column, table)).fetchall()
        ids[obs].update(r[0] for r in rows)
        steps.append({'table': table, 'rows': len(rows)})
    for obs, wanted in ids.items():
        found = {r[0] for r in conn.execute('SELECT id FROM old.%s' % obs)} & wanted
        if found != wanted:
            raise ValueError('A baseline cites %s ids that do not exist: %s' % (obs, sorted(wanted - found)))
    for table, _, _ in BASELINES:
        for row in conn.execute("SELECT * FROM old.%s WHERE baseline_state != 'VERIFIED'" % table):
            warnings.append('%s has a baseline in state %s: %s' % (table, row['baseline_state'], tuple(row)[:2]))
    for row in conn.execute('SELECT pool_name, expected_error_count FROM old.zfs_pool_baseline WHERE expected_error_count > 0'):
        warnings.append('ZFS pool %s has a baseline of %d permanent errors; 1.3 opens an incident for those on every sample' % tuple(row))
    return steps, ids, warnings


def carry(old_db, new_db, apply=False, backup_dir=None):
    if apply and backup_dir is None:
        raise ValueError('Apply requires a private backup directory')
    receipt = {'state': 'PLANNED'}
    uri = 'file:' + str(Path(new_db).resolve()) + ('?mode=rw' if apply else '?mode=ro')
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('ATTACH DATABASE ? AS old', ('file:' + str(Path(old_db).resolve()) + '?mode=ro',))
        check(conn)
        steps, ids, warnings = plan(conn)
        receipt.update(plan=steps, observations={k: len(v) for k, v in ids.items()}, warnings=warnings)
        if apply:
            directory = Path(tempfile.mkdtemp(prefix='carry-baselines-', dir=backup_dir))
            directory.chmod(0o700)
            backup = directory / 'new-state-before.db'
            with closing(sqlite3.connect(backup)) as destination:
                conn.backup(destination)
            backup.chmod(0o600)
            receipt['backup'] = str(backup)
        try:
            conn.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
            if apply:
                for obs in OBSERVATION_TABLES:
                    for oid in sorted(ids[obs]):
                        conn.execute('INSERT INTO main.%s SELECT * FROM old.%s WHERE id=?' % (obs, obs), (oid,))
                for table, _, _ in BASELINES:
                    conn.execute('INSERT INTO main.%s SELECT * FROM old.%s' % (table, table))
                receipt['copied'] = {}
                for table, _, _ in BASELINES:
                    got, want = _count(conn, 'main', table), _count(conn, 'old', table)
                    if got != want:
                        raise RuntimeError('Row count for %s differs after the copy; rolled back' % table)
                    receipt['copied'][table] = got
                for obs in OBSERVATION_TABLES:
                    if _count(conn, 'main', obs) != len(ids[obs]):
                        raise RuntimeError('Observation count for %s differs after the copy; rolled back' % obs)
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
    p.add_argument('--old-db', required=True, type=Path)
    p.add_argument('--new-db', required=True, type=Path)
    p.add_argument('--backup-dir', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    if a.apply and os.geteuid() != 0:
        p.error('Apply is an operator action requiring root')
    try:
        print(json.dumps(carry(a.old_db, a.new_db, a.apply, a.backup_dir), indent=2))
    except ValueError as exc:
        raise SystemExit('REFUSED: %s' % exc)


if __name__ == '__main__':
    main()
