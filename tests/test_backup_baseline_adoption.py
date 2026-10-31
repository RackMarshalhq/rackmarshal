from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from rackmarshal.db.migrations import migrate

spec = importlib.util.spec_from_file_location('adoption', Path('scripts/adopt-backup-baseline.py'))
adoption = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adoption)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
EPOCH = NOW.timestamp()
H = 3600


def snap(age_h=2, state='ok'):
    return {'backup_type': 'vm', 'backup_id': '100', 'backup_time': int(EPOCH - age_h * H),
            'verification_state': state}


def guest(vmid, name, kind='vm', **over):
    g = {'vmid': vmid, 'name': name, 'guest_type': kind, 'node': 'n1', 'guest_status': 'running',
         'policy_included': True, 'snapshot_present': True, 'latest_snapshot': snap()}
    g.update(over)
    return g


JOB = {'id': 'backup-abc', 'enabled': True, 'node': None, 'mode': 'snapshot', 'storage': 'pbs',
       'schedule': '02:00', 'vmids': [100, 101], 'notes_template': '{{guestname}}',
       'prune': {'keep_daily': 7, 'keep_last': None, 'keep_weekly': 4, 'keep_monthly': None,
                 'keep_yearly': None}}


def payload(**over):
    p = {'schema_version': 1, 'collector': 'backup_domain', 'resource_count': 2,
         'backup_jobs': [dict(JOB, node='n1')], 'recent_vzdump_tasks': [],
         'resources': [guest(100, 'alpha'), guest(101, 'beta', 'ct')]}
    p.update(over)
    return p


class BackupBaselineAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.db = self.root / 'fixture.db'
        self.conf = self.root / 'rackmarshal.conf'
        self.conf.write_text('STATE_DB=%s\nLOCAL_AI_ENABLED=false\n' % self.db)
        with closing(sqlite3.connect(self.db)) as c:
            for sql in migrate.discover_sql(migrate.MIG_DIR):
                c.executescript(sql.read_text())
            self.put(c, 1, payload())
            c.commit()

    def put(self, c, oid, pl, observed='2026-01-01T11:30:00Z', collector='backup_domain'):
        c.execute('INSERT INTO observations(id,collector,observed_at,source,schema_version,tls_verified,'
                  'resource_count,payload_json) VALUES(?,?,?,?,?,?,?,?)',
                  (oid, collector, observed, 't', 1, 1, 2, json.dumps(pl)))

    def set_payload(self, pl, observed=None, collector=None):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('DELETE FROM observations WHERE id=1')
            self.put(c, 1, pl, **({'observed': observed} if observed else {}),
                     **({'collector': collector} if collector else {}))
            c.commit()

    def call(self, vmids=None, apply=False, job='backup-abc', age=36, note='I checked PBS 2026-01-01'):
        return adoption.adopt(self.db, 1, job, [100, 101] if vmids is None else vmids, age, note,
                              apply, self.root, NOW)

    def counts(self):
        with closing(sqlite3.connect(self.db)) as c:
            return (c.execute('SELECT COUNT(*) FROM backup_job_baseline').fetchone()[0],
                    c.execute('SELECT COUNT(*) FROM backup_guest_baseline').fetchone()[0])

    def test_plan_does_not_write(self):
        r = self.call()
        self.assertEqual(r['state'], 'PLANNED')
        self.assertEqual(self.counts(), (0, 0))

    def test_apply_inserts_job_and_guests_and_backs_up(self):
        r = self.call(apply=True)
        self.assertEqual((r['state'], self.counts()), ('APPLIED', (1, 2)))
        with closing(sqlite3.connect(r['backup'])) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM backup_guest_baseline').fetchone()[0], 0)
        with closing(sqlite3.connect(self.db)) as c:
            job = c.execute('SELECT expected_node,expected_keep_daily,expected_keep_last,expected_schedule '
                            'FROM backup_job_baseline').fetchone()
            self.assertEqual(job, ('n1', '7', None, '02:00'))
            g = c.execute('SELECT display_name,guest_type,max_snapshot_age_hours,expected_job_id,'
                          'expected_verification_state FROM backup_guest_baseline ORDER BY vmid').fetchall()
            self.assertEqual(g, [('alpha', 'vm', 36.0, 'backup-abc', 'ok'),
                                 ('beta', 'ct', 36.0, 'backup-abc', 'ok')])
        self.assertTrue((Path(r['backup']).parent / 'receipt.json').exists())

    def test_adopted_baseline_compares_as_normal(self):
        self.call(apply=True)
        # comparator runs at the observation's own time; use a copy whose snapshot is fresh relative to it
        results = self.compare()
        for key in (('backup_job', 'backup-abc'), ('backup_guest', '100'), ('backup_guest', '101')):
            self.assertEqual(results[key]['outcome'], 'MATCH', results[key])

    def test_changed_job_is_detected_after_adoption(self):
        self.call(apply=True)
        pl = payload(backup_jobs=[dict(JOB, node='n1', schedule='05:00')])
        self.set_payload(pl)
        results = self.compare()
        self.assertEqual(results[('backup_job', 'backup-abc')]['outcome'], 'STATUS-CHANGED')

    def compare(self):
        env = dict(os.environ, PYTHONPATH=str(Path.cwd()), RACKMARSHAL_CONFIG=str(self.conf))
        out = subprocess.run(
            [sys.executable, '-m', 'rackmarshal.domains.backup.comparator', '--observation-id', '1',
             '--database', str(self.db)], capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return {(r['resource_type'], r['resource_key']): r for r in json.loads(out.stdout)['results']}

    def refuse(self, pattern, **kw):
        with self.assertRaisesRegex(ValueError, pattern):
            self.call(apply=True, **kw)
        self.assertEqual(self.counts(), (0, 0))

    def test_missing_guest_prevents_partial_batch(self):
        self.refuse('missing from the observation', vmids=[100, 999])

    def test_unknown_job(self):
        self.refuse('not found exactly once', job='nope')

    def test_empty_or_duplicate_scope_and_note(self):
        self.refuse('guest scope', vmids=[])
        self.refuse('guest scope', vmids=[100, 100])
        self.refuse('approval note', note='  ')

    def test_age_limit_must_be_sane(self):
        self.refuse('maximum backup age', age=0)
        self.refuse('maximum backup age', age=-3)
        self.refuse('maximum backup age', age=24 * 31)

    def test_refuses_baselining_a_bad_state(self):
        base = payload()
        cases = {
            'not covered': guest(100, 'alpha', policy_included=False),
            'no backup yet': guest(100, 'alpha', snapshot_present=False, latest_snapshot=None),
            'not verified ok': guest(100, 'alpha', latest_snapshot=snap(state='failed')),
            'outside the 36 hour limit': guest(100, 'alpha', latest_snapshot=snap(age_h=50)),
            'no type or name': guest(100, ''),
        }
        for pattern, g in cases.items():
            self.set_payload(dict(base, resources=[g, guest(101, 'beta', 'ct')]))
            self.refuse(pattern)

    def test_refuses_disabled_job(self):
        self.set_payload(payload(backup_jobs=[dict(JOB, node='n1', enabled=False)]))
        self.refuse('not enabled')

    def test_refuses_job_without_required_fields(self):
        self.set_payload(payload(backup_jobs=[dict(JOB, node='n1', storage=None)]))
        self.refuse('no storage')

    def test_stale_or_wrong_observation(self):
        self.set_payload(payload(), observed='2026-01-01T08:00:00Z')
        self.refuse('fresh')
        self.set_payload(payload(), collector='pve_cluster_resources')
        self.refuse('backup_domain observation')

    def test_existing_baseline_cannot_be_overwritten(self):
        self.call(apply=True)
        with self.assertRaisesRegex(ValueError, 'Existing baseline must not be overwritten'):
            self.call(apply=True)
        self.assertEqual(self.counts(), (1, 2))

    def test_second_job_baseline_refused(self):
        self.call(vmids=[100], apply=True)
        self.set_payload(payload(backup_jobs=[dict(JOB, node='n1'), dict(JOB, node='n1', id='other')]))
        with self.assertRaisesRegex(ValueError, 'already exists'):
            adoption.adopt(self.db, 1, 'other', [101], 36, 'x', True, self.root, NOW)
        self.assertEqual(self.counts(), (1, 1))

    def test_database_failure_rolls_back_everything(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER reject_second BEFORE INSERT ON backup_guest_baseline "
                      "WHEN NEW.vmid=101 BEGIN SELECT RAISE(ABORT,'fixture rejection'); END")
            c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(apply=True)
        self.assertEqual(self.counts(), (0, 0))


if __name__ == '__main__':
    unittest.main()
