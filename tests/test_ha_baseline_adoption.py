"""Home Assistant baseline adoption: synthetic observations and disposable databases only."""
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

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ha_adoption', ROOT / 'scripts' / 'adopt-ha-baseline.py')
adoption = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adoption)

API = {'resource_type': 'ha_api', 'resource_key': 'home_assistant_api', 'display_name': 'Home Assistant API', 'status': 'OK', 'expected_status': 'OK'}
CORE = {'resource_type': 'ha_core', 'resource_key': 'home_assistant_core', 'display_name': 'Home Assistant Core', 'status': 'RUNNING', 'expected_status': 'RUNNING'}


class HaBaselineAdoptionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / 'state.db'
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        with closing(sqlite3.connect(self.db)) as c:
            for name in ('001_pve_ledger.sql', '002_ha_ledger.sql'):
                c.executescript((ROOT / 'rackmarshal/db/migrations' / name).read_text())
            c.commit()
        self.tick = 0
        self.observation([API, CORE])

    def observation(self, resources, observed_at=None, tls=1, collector='home_assistant'):
        self.tick += 1
        observed_at = observed_at or '2026-01-01T11:59:%02dZ' % self.tick
        payload = {'collector': collector, 'resources': resources, 'resource_count': len(resources)}
        with closing(sqlite3.connect(self.db)) as c:
            cur = c.execute('INSERT INTO observations(collector,observed_at,source,schema_version,tls_verified,resource_count,payload_json) VALUES(?,?,?,?,?,?,?)',
                            (collector, observed_at, 'fixture', 1, tls, len(resources), json.dumps(payload)))
            c.commit()
            self.last = cur.lastrowid
        return self.last

    def call(self, resources=None, apply=False, oid=1):
        return adoption.adopt(self.db, oid, resources or ['home_assistant_api', 'home_assistant_core'], 'User authorized fixture baseline', apply, self.root, self.now)

    def count(self):
        with closing(sqlite3.connect(self.db)) as c:
            return c.execute('SELECT COUNT(*) FROM ha_resource_baseline').fetchone()[0]

    def test_plan_does_not_write(self):
        self.assertEqual(self.call()['state'], 'PLANNED')
        self.assertEqual(self.count(), 0)

    def test_apply_inserts_rows_and_backs_up(self):
        receipt = self.call(apply=True)
        self.assertEqual(receipt['state'], 'APPLIED')
        self.assertEqual(self.count(), 2)
        with closing(sqlite3.connect(receipt['backup'])) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ha_resource_baseline').fetchone()[0], 0)

    def test_adopted_baseline_makes_the_comparator_report_match(self):
        conf = self.root / 'conf'
        conf.write_text('STATE_DB=%s\nSITE_NAME=fixture\n' % self.db)
        env = dict(os.environ, RACKMARSHAL_CONFIG=str(conf), RACKMARSHAL_STATE_DB=str(self.db), PYTHONPATH=str(ROOT))

        def compare():
            return subprocess.run([sys.executable, '-B', '-m', 'rackmarshal.domains.ha.comparator', '--db', str(self.db), '--observation-id', '1'],
                                  capture_output=True, text=True, env=env, cwd=ROOT)

        before = compare()
        self.assertNotEqual(before.returncode, 0)
        self.assertIn('baseline is empty', before.stderr + before.stdout)
        self.call(apply=True)
        after = compare()
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual({r['outcome'] for r in json.loads(after.stdout)['results']}, {'MATCH'})

    def refuses(self, resources, message, oid):
        with self.assertRaisesRegex(ValueError, message):
            self.call(resources, True, oid)
        self.assertEqual(self.count(), 0)

    def test_resource_not_in_expected_state_is_refused(self):
        down = dict(API, status='UNREACHABLE')
        self.refuses(['home_assistant_api'], 'not the expected OK', self.observation([down, CORE]))

    def test_missing_fields_are_refused(self):
        odd = {k: v for k, v in API.items() if k != 'expected_status'}
        self.refuses(['home_assistant_api'], 'no expected_status', self.observation([odd]))

    def test_unknown_resource_empty_and_duplicate_scope(self):
        self.refuses(['nope'], 'not in the observation', 1)
        self.refuses(['home_assistant_api', 'home_assistant_api'], 'unique resource scope', 1)

    def test_stale_untrusted_or_wrong_collector_observation_is_refused(self):
        self.refuses(['home_assistant_api'], 'fresh within', self.observation([API], observed_at='2026-01-01T10:00:00Z'))
        self.refuses(['home_assistant_api'], 'TLS', self.observation([API], tls=0))
        self.refuses(['home_assistant_api'], 'Home Assistant observation', self.observation([API], collector='pve_cluster_resources'))

    def test_existing_baseline_is_never_overwritten(self):
        self.call(['home_assistant_api'], True)
        with self.assertRaisesRegex(ValueError, 'must not be overwritten'):
            self.call(['home_assistant_api'], True)
        self.assertEqual(self.count(), 1)

    def test_database_failure_rolls_back_every_insert(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER reject_core BEFORE INSERT ON ha_resource_baseline WHEN NEW.resource_key='home_assistant_core' BEGIN SELECT RAISE(ABORT,'fixture rejection'); END")
            c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(apply=True)
        self.assertEqual(self.count(), 0)


if __name__ == '__main__':
    unittest.main()
