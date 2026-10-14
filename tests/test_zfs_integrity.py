"""Synthetic collector/ledger regressions; no ZFS host or SSH is contacted."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ZFSIntegrityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / 'state.db'
        conf = self.root / 'conf'
        conf.write_text(f'STATE_DB={self.db}\nSITE_NAME=fixture\nZFS_SSH_HOST=fixture\nZFS_SSH_USER=fixture\nZFS_SSH_KEY=/fixture/key\nZFS_KNOWN_HOSTS=/fixture/hosts\n')
        self.env = dict(os.environ, RACKMARSHAL_CONFIG=str(conf), RACKMARSHAL_STATE_DB=str(self.db))
        self.run_module('rackmarshal.db.migrations.migrate', ['--db', str(self.db), '--apply', '--yes'], decode=False)
        self.connection = sqlite3.connect(self.db)
        self.addCleanup(self.connection.close)
        self.sequence = 0
        self.run_module('rackmarshal.domains.zfs.observation', payload=self.payload('ONLINE', 0))
        self.connection.execute("INSERT INTO zfs_pool_baseline(pool_name,pool_guid,baseline_state,expected_state,expected_error_count,source_observation_id) VALUES('fixture','1','VERIFIED','ONLINE',0,1)")
        self.connection.commit()

    def run_module(self, module, args=(), payload=None, decode=True):
        result = subprocess.run([sys.executable, '-m', module, *args],
                                input=json.dumps(payload) if payload is not None else None,
                                text=True, capture_output=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout) if decode else result.stdout

    def payload(self, state, count, guid='1'):
        self.sequence += 1
        return {'schema_version': 1, 'collector': 'zfs_status',
                'observed_at': f'2026-01-01T00:{self.sequence:02d}:00Z',
                'source': 'synthetic', 'host_key_verified': True, 'pool_count': 1,
                'pools': [{'name': 'fixture', 'pool_guid': guid, 'state': state,
                           'error_count': count, 'vdevs': []}]}

    def process(self, payload):
        oid = self.run_module('rackmarshal.domains.zfs.observation', payload=payload)['observation_id']
        args = ['--database', str(self.db)]
        comparison = self.run_module('rackmarshal.domains.zfs.comparator', args + ['--observation-id', str(oid)])
        self.run_module('rackmarshal.domains.zfs.events', args, comparison)
        result = self.run_module('rackmarshal.domains.zfs.incidents', args, comparison)
        return comparison, result

    def cycle(self, state, count, guid='1'):
        return self.process(self.payload(state, count, guid))

    def open_count(self):
        return self.connection.execute("SELECT COUNT(*) FROM zfs_incidents WHERE incident_state='OPEN'").fetchone()[0]

    def test_degraded_to_online_corruption_persists_until_explicit_clean(self):
        self.cycle('DEGRADED', 0)
        for _ in range(2):
            comparison, result = self.cycle('ONLINE', 11)
            self.assertEqual(comparison['results'][0]['outcome'], 'STATUS-CHANGED')
            self.assertEqual(comparison['results'][0]['integrity_state'], 'PROBLEM')
            self.assertEqual(result['incidents_recovered'], 0)
            self.assertEqual(self.open_count(), 1)
        self.assertEqual(self.connection.execute('SELECT occurrence_count FROM zfs_incidents').fetchone()[0], 3)
        _, result = self.cycle('ONLINE', 0)
        self.assertEqual(result['incidents_recovered'], 1)
        self.assertEqual(self.open_count(), 0)

    def test_positive_baseline_cannot_normalize_permanent_corruption(self):
        self.connection.execute('UPDATE zfs_pool_baseline SET expected_error_count=11')
        self.connection.commit()
        self.cycle('ONLINE', 11)
        self.assertEqual(self.open_count(), 1)
        _, result = self.cycle('ONLINE', 0)
        self.assertEqual(result['incidents_recovered'], 1)

    def test_missing_or_null_count_preserves_open_incident(self):
        self.cycle('ONLINE', 11)
        for absent in (False, True):
            payload = self.payload('ONLINE', None)
            if absent:
                del payload['pools'][0]['error_count']
            comparison, result = self.process(payload)
            self.assertEqual(comparison['results'][0]['integrity_state'], 'UNKNOWN')
            self.assertEqual(result['incidents_recovered'], 0)
            self.assertEqual(self.open_count(), 1)

    def test_missing_count_without_incident_is_not_clean(self):
        comparison, _ = self.cycle('ONLINE', None)
        self.assertEqual(comparison['results'][0]['integrity_state'], 'UNKNOWN')
        self.assertNotEqual(comparison['results'][0]['outcome'], 'MATCH')

    def test_wrong_identity_or_degraded_zero_does_not_recover(self):
        self.cycle('ONLINE', 11)
        for state, guid in [('ONLINE', '2'), ('DEGRADED', '1')]:
            _, result = self.cycle(state, 0, guid)
            self.assertEqual(result['incidents_recovered'], 0)
        self.assertEqual(self.open_count(), 1)

    def test_abnormal_classification_change_is_not_recovery(self):
        payload = self.payload('ONLINE', 0)
        payload.update(pool_count=0, pools=[])
        self.process(payload)
        _, result = self.cycle('ONLINE', 11)
        self.assertEqual(result['incidents_recovered'], 0)
        self.assertEqual(self.open_count(), 1)
        _, result = self.cycle('ONLINE', 0)
        self.assertEqual(result['incidents_recovered'], 1)

    def test_forged_match_without_recorded_clean_evidence_cannot_close(self):
        self.cycle('ONLINE', 11)
        payload = self.payload('ONLINE', None)
        oid = self.run_module('rackmarshal.domains.zfs.observation', payload=payload)['observation_id']
        comparison = {'schema_version': 1, 'comparator': 'zfs_baseline', 'observation_id': oid,
                      'observed_at': payload['observed_at'], 'results': [{'resource_type': 'zfs_pool',
                      'resource_key': 'fixture', 'baseline_state': 'VERIFIED', 'outcome': 'MATCH'}]}
        result = self.run_module('rackmarshal.domains.zfs.incidents', ['--database', str(self.db)], comparison)
        self.assertEqual(result['incidents_recovered'], 0)

    def load_collector(self):
        with patch.dict(os.environ, self.env):
            spec = importlib.util.spec_from_file_location('zfs_collector_fixture', ROOT / 'rackmarshal/domains/zfs/collector.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_collector_preserves_missing_and_parses_decimal_counts(self):
        collector = self.load_collector()
        for value, expected in [(None, None), (0, 0), ('0', 0), (11, 11), ('11', 11)]:
            pool = {'state': 'ONLINE', 'pool_guid': '1'}
            if value is not None:
                pool['error_count'] = value
            output = io.StringIO()
            with patch.object(collector, 'run_zpool_status', return_value={'pools': {'fixture': pool}}), redirect_stdout(output):
                collector.main()
            self.assertEqual(json.loads(output.getvalue())['pools'][0]['error_count'], expected)

    def test_collector_rejects_lossy_or_invalid_counts(self):
        collector = self.load_collector()
        for value in (True, False, -1, 0.5, 0.0, '0.5', '-1', '', [], {}):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                collector.permanent_error_count(value, 'fixture')

    def test_ingestion_rejects_noncanonical_counts(self):
        for value in (True, False, -1, 0.5, '0', [], {}):
            result = subprocess.run([sys.executable, '-m', 'rackmarshal.domains.zfs.observation'],
                                    input=json.dumps(self.payload('ONLINE', value)), env=self.env,
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0, value)


if __name__ == '__main__':
    unittest.main()
