"""ZFS baseline adoption: synthetic observations and disposable databases only."""
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
spec = importlib.util.spec_from_file_location('zfs_adoption', ROOT / 'scripts' / 'adopt-zfs-baseline.py')
adoption = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adoption)


def vdev(name, kind, state='ONLINE', children=None, read=0, write=0, checksum=0):
    item = {'name': name, 'type': kind, 'state': state, 'read_errors': read,
            'write_errors': write, 'checksum_errors': checksum, 'slow_ios': None,
            'path': '/dev/' + name if kind == 'disk' else None, 'phys_path': None}
    if children is not None:
        item['children'] = children
    return item


def pool(name, guid, state='ONLINE', count=0, vdevs=None):
    body = {'name': name, 'pool_guid': guid, 'state': state, 'vdevs': vdevs if vdevs is not None else [
        vdev(name, 'root', children=[vdev('mirror-0', 'mirror', children=[vdev('sda', 'disk'), vdev('sdb', 'disk')])])]}
    if count is not False:
        body['error_count'] = count
    return body


class ZfsBaselineAdoptionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / 'state.db'
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript((ROOT / 'rackmarshal/db/migrations/003_zfs_ledger.sql').read_text())
            c.commit()
        self.tick = 0
        self.observation([pool('tank', '111'), pool('spare', '222')])

    def observation(self, pools, observed_at=None, verified=1):
        self.tick += 1
        observed_at = observed_at or '2026-01-01T11:59:%02dZ' % self.tick
        payload = {'schema_version': 1, 'collector': 'zfs_status', 'observed_at': observed_at,
                   'source': 'fixture', 'host_key_verified': True, 'pool_count': len(pools), 'pools': pools}
        with closing(sqlite3.connect(self.db)) as c:
            cur = c.execute('INSERT INTO zfs_observations(observed_at,source,schema_version,host_key_verified,pool_count,payload_json) VALUES(?,?,?,?,?,?)',
                            (observed_at, 'fixture', 1, verified, len(pools), json.dumps(payload)))
            c.commit()
            self.last = cur.lastrowid
        return self.last

    def call(self, pools=None, apply=False, oid=1):
        return adoption.adopt(self.db, oid, pools or ['tank'], 'User authorized fixture baseline', apply, self.root, self.now)

    def count(self, table='zfs_pool_baseline'):
        with closing(sqlite3.connect(self.db)) as c:
            return c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]

    def test_plan_does_not_write(self):
        receipt = self.call()
        self.assertEqual(receipt['state'], 'PLANNED')
        self.assertEqual((self.count(), self.count('zfs_vdev_baseline')), (0, 0))
        self.assertEqual(len(receipt['pool_rows']), 1)
        self.assertEqual(len(receipt['vdev_rows']), 4)

    def test_apply_inserts_scoped_rows_and_backs_up(self):
        receipt = self.call(apply=True)
        self.assertEqual(receipt['state'], 'APPLIED')
        self.assertEqual((self.count(), self.count('zfs_vdev_baseline')), (1, 4))
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute('SELECT pool_name,baseline_state,expected_error_count FROM zfs_pool_baseline').fetchall(), [('tank', 'VERIFIED', 0)])
        with closing(sqlite3.connect(receipt['backup'])) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM zfs_pool_baseline').fetchone()[0], 0)
        self.assertTrue((Path(receipt['backup']).parent / 'receipt.json').is_file())

    def test_adopted_baseline_makes_the_comparator_report_match(self):
        conf = self.root / 'conf'
        conf.write_text('STATE_DB=%s\nSITE_NAME=fixture\n' % self.db)
        env = dict(os.environ, RACKMARSHAL_CONFIG=str(conf), RACKMARSHAL_STATE_DB=str(self.db), PYTHONPATH=str(ROOT))

        def compare():
            result = subprocess.run([sys.executable, '-B', '-m', 'rackmarshal.domains.zfs.comparator', '--database', str(self.db), '--observation-id', '1'],
                                    capture_output=True, text=True, env=env, cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stderr)
            return {r['resource_key']: r['outcome'] for r in json.loads(result.stdout)['results']}

        before = compare()
        self.assertEqual(before['tank'], 'NEW')
        self.assertEqual(before['spare'], 'NEW')
        self.call(apply=True)
        after = compare()
        self.assertEqual(after['tank'], 'MATCH')
        self.assertEqual(after['spare'], 'NEW')
        self.assertTrue(all(v == 'MATCH' for k, v in after.items() if k.startswith('tank/')), after)

    def refuses(self, pools, message, oid=None):
        with self.assertRaisesRegex(ValueError, message):
            self.call(pools, True, oid or self.last)
        self.assertEqual((self.count(), self.count('zfs_vdev_baseline')), (0, 0))

    def test_permanent_errors_are_not_adopted(self):
        self.refuses(['bad'], 'zero permanent errors', self.observation([pool('bad', '3', count=7)]))

    def test_unknown_error_count_is_not_adopted(self):
        self.refuses(['unk'], 'zero permanent errors', self.observation([pool('unk', '4', count=False)]))

    def test_degraded_pool_is_not_adopted(self):
        self.refuses(['deg'], 'not ONLINE', self.observation([pool('deg', '5', state='DEGRADED')]))

    def test_degraded_vdev_is_not_adopted(self):
        broken = [vdev('v', 'root', children=[vdev('sda', 'disk', state='FAULTED')])]
        self.refuses(['v'], 'is not ONLINE', self.observation([pool('v', '6', vdevs=broken)]))

    def test_vdev_without_integer_counters_is_not_adopted(self):
        odd = vdev('sda', 'disk')
        odd['read_errors'] = None
        self.refuses(['w'], 'integer read_errors', self.observation([pool('w', '7', vdevs=[odd])]))

    def test_missing_pool_empty_scope_and_duplicate_scope(self):
        self.refuses(['nope'], 'not in the observation', 1)
        self.refuses(['tank', 'tank'], 'unique pool scope', 1)

    def test_stale_or_unverified_observation_is_rejected(self):
        self.refuses(['tank'], 'fresh within', self.observation([pool('tank', '111')], observed_at='2026-01-01T10:00:00Z'))
        self.refuses(['tank'], 'host key', self.observation([pool('tank', '111')], verified=0))

    def test_existing_baseline_is_never_overwritten(self):
        self.call(apply=True)
        with self.assertRaisesRegex(ValueError, 'must not be overwritten'):
            self.call(apply=True)
        self.assertEqual((self.count(), self.count('zfs_vdev_baseline')), (1, 4))

    def test_database_failure_rolls_back_every_insert(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER reject_sdb BEFORE INSERT ON zfs_vdev_baseline WHEN NEW.vdev_name='sdb' BEGIN SELECT RAISE(ABORT,'fixture rejection'); END")
            c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(apply=True)
        self.assertEqual((self.count(), self.count('zfs_vdev_baseline')), (0, 0))


if __name__ == '__main__':
    unittest.main()
