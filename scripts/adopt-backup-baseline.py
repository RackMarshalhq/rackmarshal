#!/usr/bin/env python3
"""Operator-only, insert-only backup baseline adoption from a pinned observation.

Records ONE backup job and the guests you name as the normal state. Not an
Investigator/MCP capability. Prints a plan and writes nothing without --apply.
The caller supplies the job, the guests, how old a backup may get (a choice only
the operator can make), an approval note, a fresh observation ID and a private
backup directory.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile

MAX_OBSERVATION_AGE_S = 7200  # the backup collector runs hourly
MAX_ALLOWED_AGE_HOURS = 24 * 30


def _prune_text(value):
    return None if value is None else str(value)


def propose(conn, observation_id, job_id, vmids, max_age_hours, note, now=None):
    if not isinstance(note, str) or not note.strip():
        raise ValueError('Require a nonempty approval note')
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError('Require the backup job id')
    if not vmids or len(vmids) != len(set(vmids)):
        raise ValueError('Require a nonempty, unique guest scope')
    if isinstance(max_age_hours, bool) or not isinstance(max_age_hours, (int, float)) \
            or not 0 < max_age_hours <= MAX_ALLOWED_AGE_HOURS:
        raise ValueError('Require a maximum backup age between 0 and %d hours' % MAX_ALLOWED_AGE_HOURS)
    obs = conn.execute('SELECT * FROM observations WHERE id=?', (observation_id,)).fetchone()
    if obs is None or obs['collector'] != 'backup_domain':
        raise ValueError('Require a recorded backup_domain observation')
    observed = datetime.fromisoformat(obs['observed_at'].replace('Z', '+00:00'))
    if observed.tzinfo is None:
        raise ValueError('Observation timezone missing')
    current = now or datetime.now(timezone.utc)
    age = (current - observed).total_seconds()
    if age < -60 or age > MAX_OBSERVATION_AGE_S:
        raise ValueError('Observation must be fresh within %d seconds' % MAX_OBSERVATION_AGE_S)
    payload = json.loads(obs['payload_json'])

    jobs = [j for j in payload.get('backup_jobs', []) if isinstance(j, dict) and j.get('id') == job_id]
    if len(jobs) != 1:
        raise ValueError('Backup job not found exactly once in the observation: ' + job_id)
    job = jobs[0]
    if job.get('enabled') is not True:
        raise ValueError('Backup job is not enabled; fix it before recording it as normal')
    for field in ('node', 'mode', 'storage', 'schedule'):
        if not isinstance(job.get(field), str) or not job[field]:
            raise ValueError('Backup job has no %s; cannot record it' % field)
    prune = job.get('prune') if isinstance(job.get('prune'), dict) else {}
    job_row = {
        'job_id': job_id, 'baseline_state': 'VERIFIED', 'expected_enabled': 1,
        'expected_node': job['node'], 'expected_mode': job['mode'],
        'expected_storage': job['storage'], 'expected_schedule': job['schedule'],
        'expected_notes_template': job.get('notes_template'),
        'expected_keep_daily': _prune_text(prune.get('keep_daily')),
        'expected_keep_last': _prune_text(prune.get('keep_last')),
        'expected_keep_weekly': _prune_text(prune.get('keep_weekly')),
        'expected_keep_monthly': _prune_text(prune.get('keep_monthly')),
        'expected_keep_yearly': _prune_text(prune.get('keep_yearly')),
        'source_observation_id': observation_id, 'note': note,
    }

    observed_guests = {}
    for item in payload.get('resources', []):
        if isinstance(item, dict) and type(item.get('vmid')) is int:
            if item['vmid'] in observed_guests:
                raise ValueError('Duplicate observed guest identity')
            observed_guests[item['vmid']] = item
    guest_rows = []
    for vmid in vmids:
        if type(vmid) is not int or vmid <= 0:
            raise ValueError('Guests must be positive numeric ids')
        item = observed_guests.get(vmid)
        if item is None:
            raise ValueError('Selected guest missing from the observation: %d' % vmid)
        if item.get('guest_type') not in ('vm', 'ct') or not item.get('name'):
            raise ValueError('Selected guest has no type or name: %d' % vmid)
        if item.get('policy_included') is not True:
            raise ValueError('Selected guest is not covered by a backup job: %d' % vmid)
        snapshot = item.get('latest_snapshot')
        if not isinstance(snapshot, dict) or item.get('snapshot_present') is not True:
            raise ValueError('Selected guest has no backup yet: %d' % vmid)
        if snapshot.get('verification_state') != 'ok':
            raise ValueError('Selected guest latest backup is not verified ok: %d' % vmid)
        stamp = snapshot.get('backup_time')
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            raise ValueError('Selected guest backup has no valid time: %d' % vmid)
        snapshot_age = (current.timestamp() - stamp) / 3600.0
        if snapshot_age < 0 or snapshot_age > max_age_hours:
            raise ValueError(
                'Selected guest latest backup is %.1f hours old, outside the %s hour limit: %d'
                % (snapshot_age, max_age_hours, vmid))
        if conn.execute('SELECT 1 FROM backup_guest_baseline WHERE vmid=?', (vmid,)).fetchone():
            raise ValueError('Existing baseline must not be overwritten: %d' % vmid)
        guest_rows.append({
            'vmid': vmid, 'display_name': item['name'], 'guest_type': item['guest_type'],
            'baseline_state': 'VERIFIED', 'expected_job_id': job_id,
            'expected_policy_included': 1, 'expected_snapshot_present': 1,
            'expected_verification_state': 'ok', 'max_snapshot_age_hours': float(max_age_hours),
            'source_observation_id': observation_id, 'note': note,
        })
    # The comparator supports exactly one job baseline.
    if conn.execute('SELECT 1 FROM backup_job_baseline').fetchone():
        raise ValueError('A backup job baseline already exists and must not be overwritten')
    return job_row, guest_rows


JOB_SQL = ('INSERT INTO backup_job_baseline(job_id,baseline_state,expected_enabled,expected_node,'
           'expected_mode,expected_storage,expected_schedule,expected_notes_template,expected_keep_daily,'
           'expected_keep_last,expected_keep_weekly,expected_keep_monthly,expected_keep_yearly,'
           'source_observation_id,note) VALUES(:job_id,:baseline_state,:expected_enabled,:expected_node,'
           ':expected_mode,:expected_storage,:expected_schedule,:expected_notes_template,:expected_keep_daily,'
           ':expected_keep_last,:expected_keep_weekly,:expected_keep_monthly,:expected_keep_yearly,'
           ':source_observation_id,:note)')
GUEST_SQL = ('INSERT INTO backup_guest_baseline(vmid,display_name,guest_type,baseline_state,expected_job_id,'
             'expected_policy_included,expected_snapshot_present,expected_verification_state,'
             'max_snapshot_age_hours,source_observation_id,note) VALUES(:vmid,:display_name,:guest_type,'
             ':baseline_state,:expected_job_id,:expected_policy_included,:expected_snapshot_present,'
             ':expected_verification_state,:max_snapshot_age_hours,:source_observation_id,:note)')


def _counts(conn):
    return (conn.execute('SELECT COUNT(*) FROM backup_job_baseline').fetchone()[0],
            conn.execute('SELECT COUNT(*) FROM backup_guest_baseline').fetchone()[0])


def adopt(db, observation_id, job_id, vmids, max_age_hours, note, apply=False, backup_dir=None, now=None):
    if apply and backup_dir is None:
        raise ValueError('Apply requires a private backup directory')
    receipt = {'observation_id': observation_id, 'approval_note': note, 'state': 'PLANNED'}
    with closing(sqlite3.connect('file:' + str(Path(db).resolve()) + ('?mode=rw' if apply else '?mode=ro'),
                                 uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        # Validate before creating a backup; revalidate within the write transaction.
        propose(conn, observation_id, job_id, vmids, max_age_hours, note, now)
        if apply:
            directory = Path(tempfile.mkdtemp(prefix='backup-baseline-', dir=backup_dir))
            directory.chmod(0o700)
            backup = directory / 'state-before.db'
            with closing(sqlite3.connect(backup)) as destination:
                conn.backup(destination)
            backup.chmod(0o600)
            receipt['backup'] = str(backup)
        try:
            conn.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
            job_row, guest_rows = propose(conn, observation_id, job_id, vmids, max_age_hours, note, now)
            receipt['job'] = job_row
            receipt['guests'] = guest_rows
            before = _counts(conn)
            receipt['before_counts'] = list(before)
            if apply:
                conn.execute(JOB_SQL, job_row)
                for row in guest_rows:
                    conn.execute(GUEST_SQL, row)
                after = _counts(conn)
                receipt['after_counts'] = list(after)
                if after != (before[0] + 1, before[1] + len(guest_rows)):
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
    p.add_argument('--job', required=True, help='backup job id exactly as shown in the observation')
    p.add_argument('--guest', required=True, action='append', type=int, help='VM/CT id (repeat per guest)')
    p.add_argument('--max-age-hours', required=True, type=float,
                   help='how old the newest backup of each guest may get before RackMarshal alerts')
    p.add_argument('--approval-note', required=True)
    p.add_argument('--backup-dir', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    if a.apply and os.geteuid() != 0:
        p.error('Apply is an operator action requiring root')
    print(json.dumps(adopt(a.db, a.observation_id, a.job, a.guest, a.max_age_hours, a.approval_note,
                           a.apply, a.backup_dir), indent=2))


if __name__ == '__main__':
    main()
