from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('retire', Path('scripts/retire-pve-baseline.py'))
retire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retire)


class RetirePveBaselineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.db = self.root / 'fixture.db'
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript(Path('rackmarshal/db/migrations/001_pve_ledger.sql').read_text())
            # 9001 is gone; 9002 still exists
            payload = {'resources': [{'type': 'lxc', 'vmid': 9002, 'name': 'Alive', 'status': 'running'}]}
            c.execute('INSERT INTO observations(id,collector,observed_at,source,schema_version,tls_verified,'
                      'resource_count,payload_json) VALUES(1,?,?,?,?,?,?,?)',
                      ('pve_cluster_resources', '2026-01-01T11:59:00Z', 'fixture', 1, 1, 1, json.dumps(payload)))
            for kind, key, name, status in (('lxc', '9001', 'Gone A', 'stopped'), ('lxc', '9002', 'Alive', 'running'),
                                            ('qemu', '9003', 'Gone B', 'running'), ('lxc', '9004', 'Other', 'stopped')):
                c.execute('INSERT INTO resource_baseline(resource_type,resource_key,display_name,expected_status,'
                          "baseline_state) VALUES(?,?,?,?, 'VERIFIED')", (kind, key, name, status))
            c.execute("INSERT INTO resource_incidents(resource_type,resource_key,display_name,incident_type,"
                      "incident_state,baseline_state,opened_observation_id,last_abnormal_observation_id,"
                      "opened_at,last_abnormal_at,occurrence_count) "
                      "VALUES('lxc','9001','Gone A','MISSING','OPEN','VERIFIED',1,1,'2026-01-01T11:59:00Z','2026-01-01T11:59:00Z',1)")
            c.commit()

    def call(self, resources=None, apply=False, note='Guest deleted on purpose'):
        return retire.retire(self.db, 1, resources or ['lxc:9001', 'qemu:9003'], note, apply, self.root, self.now)

    def keys(self):
        with closing(sqlite3.connect(self.db)) as c:
            return sorted(r[0] for r in c.execute('SELECT resource_key FROM resource_baseline'))

    def test_plan_does_not_write(self):
        r = self.call()
        self.assertEqual(r['state'], 'PLANNED')
        self.assertEqual(self.keys(), ['9001', '9002', '9003', '9004'])
        self.assertEqual([x['resource_key'] for x in r['rows']], ['9001', '9003'])

    def test_apply_removes_only_named_rows_and_backs_up(self):
        r = self.call(apply=True)
        self.assertEqual(r['state'], 'APPLIED')
        self.assertEqual((r['before_count'], r['after_count']), (4, 2))
        self.assertEqual(self.keys(), ['9002', '9004'])
        with closing(sqlite3.connect(r['backup'])) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM resource_baseline').fetchone()[0], 4)
        self.assertTrue((Path(r['backup']).parent / 'receipt.json').exists())

    def test_incidents_and_observations_are_never_touched(self):
        self.call(apply=True)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM resource_incidents').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 1)

    def test_guest_that_still_exists_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'still exists'):
            self.call(['lxc:9001', 'lxc:9002'], apply=True)
        self.assertEqual(self.keys(), ['9001', '9002', '9003', '9004'])

    def test_unknown_baseline_is_refused_without_partial_delete(self):
        with self.assertRaisesRegex(ValueError, 'No baseline row'):
            self.call(['lxc:9001', 'lxc:9999'], apply=True)
        self.assertEqual(self.keys(), ['9001', '9002', '9003', '9004'])

    def test_stale_observation_refused(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE observations SET observed_at='2026-01-01T10:00:00Z'")
            c.commit()
        with self.assertRaisesRegex(ValueError, 'fresh'):
            self.call(apply=True)
        self.assertEqual(len(self.keys()), 4)

    def test_unverified_tls_observation_refused(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('UPDATE observations SET tls_verified=0')
            c.commit()
        with self.assertRaisesRegex(ValueError, 'TLS'):
            self.call(apply=True)
        self.assertEqual(len(self.keys()), 4)

    def test_wrong_collector_refused(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE observations SET collector='zfs'")
            c.commit()
        with self.assertRaisesRegex(ValueError, 'PVE observation'):
            self.call(apply=True)

    def test_scope_rules(self):
        for bad in (['lxc:9001', 'lxc:9001'], ['lxc:abc'], ['vm:9001'], ['9001']):
            with self.assertRaises(ValueError):
                self.call(bad, apply=True)
        with self.assertRaises(ValueError):
            self.call(note='  ', apply=True)
        self.assertEqual(len(self.keys()), 4)

    def test_apply_needs_backup_dir(self):
        with self.assertRaisesRegex(ValueError, 'backup directory'):
            retire.retire(self.db, 1, ['lxc:9001'], 'note', True, None, self.now)

    def test_database_failure_rolls_back_every_delete(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER reject_second BEFORE DELETE ON resource_baseline "
                      "WHEN OLD.resource_key='9003' BEGIN SELECT RAISE(ABORT,'fixture rejection'); END")
            c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(apply=True)
        self.assertEqual(self.keys(), ['9001', '9002', '9003', '9004'])


if __name__ == '__main__':
    unittest.main()
