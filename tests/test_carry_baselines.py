"""One-time baseline carry-over: synthetic databases only."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('carry', ROOT / 'scripts' / 'carry-baselines.py')
carry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(carry)


def migrate(db):
    result = subprocess.run([sys.executable, '-B', '-m', 'rackmarshal.db.migrations.migrate', '--db', str(db), '--apply', '--yes'],
                            capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT), RACKMARSHAL_STATE_DB=str(db)))
    assert result.returncode == 0, result.stderr + result.stdout


class CarryBaselinesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.old, self.new = self.root / 'old.db', self.root / 'new.db'
        migrate(self.old)
        migrate(self.new)
        with closing(sqlite3.connect(self.old)) as c:
            for oid, ts in ((1, '2026-01-01T00:00:01Z'), (2, '2026-01-01T00:00:02Z'), (3, '2026-01-01T00:00:03Z')):
                c.execute('INSERT INTO observations(id,collector,observed_at,source,schema_version,tls_verified,resource_count,payload_json) VALUES(?,?,?,?,?,?,?,?)', (oid, 'fixture', ts, 'fixture', 1, 1, 0, '{}'))
            c.execute("INSERT INTO zfs_observations(id,observed_at,source,schema_version,host_key_verified,pool_count,payload_json) VALUES(7,'2026-01-01T00:00:07Z','fixture',1,1,1,'{}')")
            c.execute("INSERT INTO zfs_observations(id,observed_at,source,schema_version,host_key_verified,pool_count,payload_json) VALUES(8,'2026-01-01T00:00:08Z','fixture',1,1,1,'{}')")
            c.execute("INSERT INTO resource_baseline(resource_type,resource_key,expected_status,baseline_state,source_observation) VALUES('lxc','101','running','VERIFIED',1)")
            c.execute("INSERT INTO ha_resource_baseline(resource_key,resource_type,display_name,baseline_state,expected_status,source_observation_id) VALUES('home_assistant_api','ha_api','HA','VERIFIED','OK',2)")
            c.execute("INSERT INTO backup_job_baseline(job_id,baseline_state,expected_enabled,expected_node,expected_mode,expected_storage,expected_schedule,source_observation_id) VALUES('job1','VERIFIED',1,'n','snapshot','s','daily',1)")
            c.execute("INSERT INTO backup_guest_baseline(vmid,display_name,guest_type,baseline_state,expected_job_id,expected_policy_included,expected_snapshot_present,expected_verification_state,max_snapshot_age_hours,source_observation_id) VALUES(101,'g','ct','VERIFIED','job1',1,1,'ok',30,1)")
            c.execute("INSERT INTO zfs_pool_baseline(pool_name,pool_guid,baseline_state,expected_state,expected_error_count,source_observation_id) VALUES('tank','1','VERIFIED','ONLINE',0,7)")
            c.execute("INSERT INTO zfs_vdev_baseline(pool_name,vdev_name,vdev_type,baseline_state,expected_state,expected_read_errors,expected_write_errors,expected_checksum_errors,source_observation_id) VALUES('tank','sda','disk','VERIFIED','ONLINE',0,0,0,7)")
            c.commit()

    def counts(self, db):
        with closing(sqlite3.connect(db)) as c:
            return {t: c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in [b[0] for b in carry.BASELINES] + ['observations', 'zfs_observations']}

    def test_plan_does_not_write(self):
        receipt = carry.carry(self.old, self.new)
        self.assertEqual(receipt['state'], 'PLANNED')
        self.assertEqual(receipt['observations'], {'observations': 2, 'zfs_observations': 1})
        self.assertTrue(all(v == 0 for v in self.counts(self.new).values()))

    def test_apply_copies_baselines_and_only_cited_observations(self):
        receipt = carry.carry(self.old, self.new, True, self.root)
        self.assertEqual(receipt['state'], 'APPLIED')
        got = self.counts(self.new)
        self.assertEqual(got, {'resource_baseline': 1, 'ha_resource_baseline': 1, 'backup_job_baseline': 1, 'backup_guest_baseline': 1,
                               'zfs_pool_baseline': 1, 'zfs_vdev_baseline': 1, 'observations': 2, 'zfs_observations': 1})
        with closing(sqlite3.connect(self.new)) as c:
            self.assertEqual([r[0] for r in c.execute('SELECT id FROM observations ORDER BY id')], [1, 2])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        with closing(sqlite3.connect(receipt['backup'])) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM zfs_pool_baseline').fetchone()[0], 0)
        with closing(sqlite3.connect(self.old)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM zfs_pool_baseline').fetchone()[0], 1)

    def test_new_database_must_be_fresh(self):
        carry.carry(self.old, self.new, True, self.root)
        with self.assertRaisesRegex(ValueError, 'fresh database'):
            carry.carry(self.old, self.new, True, self.root)

    def test_new_database_with_observations_is_refused(self):
        with closing(sqlite3.connect(self.new)) as c:
            c.execute("INSERT INTO observations(collector,observed_at,source,schema_version,tls_verified,resource_count,payload_json) VALUES('x','2026-02-01T00:00:00Z','x',1,1,0,'{}')")
            c.commit()
        with self.assertRaisesRegex(ValueError, 'fresh database'):
            carry.carry(self.old, self.new, True, self.root)
        self.assertEqual(self.counts(self.new)['resource_baseline'], 0)

    def test_different_schema_versions_are_refused(self):
        with closing(sqlite3.connect(self.new)) as c:
            c.execute("UPDATE schema_migrations SET checksum='changed' WHERE id='001_pve_ledger'")
            c.commit()
        with self.assertRaisesRegex(ValueError, 'different schema versions'):
            carry.carry(self.old, self.new, True, self.root)

    def test_a_table_that_differs_between_the_databases_is_refused(self):
        with closing(sqlite3.connect(self.new)) as c:
            c.execute('ALTER TABLE zfs_pool_baseline ADD COLUMN surprise TEXT')
            c.commit()
        with self.assertRaisesRegex(ValueError, 'differs between'):
            carry.carry(self.old, self.new, True, self.root)
        self.assertEqual(self.counts(self.new)['zfs_pool_baseline'], 0)

    def test_baseline_citing_a_missing_observation_is_refused(self):
        with closing(sqlite3.connect(self.old)) as c:
            c.execute('PRAGMA foreign_keys=OFF')
            c.execute('DELETE FROM observations WHERE id=2')
            c.commit()
        with self.assertRaisesRegex(ValueError, 'do not exist'):
            carry.carry(self.old, self.new, True, self.root)

    def test_database_failure_rolls_back_everything(self):
        with closing(sqlite3.connect(self.new)) as c:
            c.execute("CREATE TRIGGER reject_vdev BEFORE INSERT ON zfs_vdev_baseline BEGIN SELECT RAISE(ABORT,'fixture rejection'); END")
            c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            carry.carry(self.old, self.new, True, self.root)
        self.assertTrue(all(v == 0 for v in self.counts(self.new).values()))

    def test_warnings_for_unverified_and_error_baselines(self):
        with closing(sqlite3.connect(self.old)) as c:
            c.execute("UPDATE zfs_pool_baseline SET expected_error_count=3")
            c.execute("UPDATE backup_job_baseline SET baseline_state='KNOWN-ISSUE'")
            c.commit()
        warnings = carry.carry(self.old, self.new)['warnings']
        self.assertTrue(any('permanent errors' in w for w in warnings))
        self.assertTrue(any('KNOWN-ISSUE' in w for w in warnings))


if __name__ == '__main__':
    unittest.main()
