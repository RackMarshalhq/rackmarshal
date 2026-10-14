"""Integrity evidence remains visible independently of incident and pool availability."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from rackmarshal.api.v1 import route

ROOT = Path(__file__).resolve().parents[1]


class ZfsStatusIntegrityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        config = root / 'config'
        config.write_text(f'STATE_DB={root / "state.db"}\nSTATUS_API_LISTEN_ADDRESS=127.0.0.1\nSTATUS_API_LISTEN_PORT=9110\n')
        with patch.dict(os.environ, {'RACKMARSHAL_CONFIG': str(config)}):
            spec = importlib.util.spec_from_file_location('zfs_status_fixture', ROOT / 'rackmarshal/api/status.py')
            self.status = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.status)
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE zfs_observations(id INTEGER PRIMARY KEY, observed_at TEXT, payload_json TEXT)')

    def summarize(self, pools):
        self.db.execute('INSERT INTO zfs_observations(observed_at,payload_json) VALUES (?,?)',
                        ('2026-01-01T00:00:00Z', json.dumps({'pools': pools})))
        return self.status.zfs_integrity_summary(self.db)

    def test_availability_and_integrity_are_independent(self):
        actual = self.summarize([{'name': 'fixture', 'state': 'ONLINE', 'error_count': 11}])
        self.assertEqual(actual['state'], 'PROBLEM')
        self.assertEqual(actual['pools'][0], {'pool_name': 'fixture', 'availability_state': 'ONLINE',
                         'integrity_state': 'PROBLEM', 'permanent_error_count': 11})
        self.assertEqual(actual['observation_id'], 1)
        self.assertEqual(actual['observed_at'], '2026-01-01T00:00:00Z')
        actual = self.summarize([{'name': 'fixture', 'state': 'DEGRADED', 'error_count': 0}])
        self.assertEqual(actual['state'], 'CLEAN')
        self.assertEqual(actual['pools'][0]['availability_state'], 'DEGRADED')

    def test_missing_and_invalid_counts_are_unknown(self):
        for count in (None, True, False, -1, 0.5, '0', [], {}):
            with self.subTest(count=count):
                actual = self.summarize([{'name': 'fixture', 'state': 'ONLINE', 'error_count': count}])
                self.assertEqual(actual['state'], 'UNKNOWN')
                self.assertIsNone(actual['pools'][0]['permanent_error_count'])
        self.assertEqual(self.summarize([{'name': 'fixture', 'state': 'ONLINE'}])['state'], 'UNKNOWN')

    def test_missing_malformed_and_empty_evidence_is_unknown(self):
        self.assertEqual(self.status.zfs_integrity_summary(self.db)['state'], 'UNKNOWN')
        for raw in ('invalid', 'null', '{}', '{"pools":{}}', '{"pools":[]}', '{"pools":[null]}'):
            self.db.execute('INSERT INTO zfs_observations(payload_json) VALUES (?)', (raw,))
            self.assertEqual(self.status.zfs_integrity_summary(self.db)['state'], 'UNKNOWN')

    def test_positive_errors_dominate_unknown_aggregate(self):
        pools = [{'name': 'a', 'error_count': None}, {'name': 'b', 'error_count': 11}]
        self.assertEqual(self.summarize(pools)['state'], 'PROBLEM')
        pools[1]['error_count'] = 0
        self.assertEqual(self.summarize(pools)['state'], 'UNKNOWN')
        pools[0]['error_count'] = 0
        self.assertEqual(self.summarize(pools)['state'], 'CLEAN')

    def test_v1_status_and_domain_routes_preserve_integrity_and_incident_status(self):
        summary = self.summarize([{'name': 'fixture', 'state': 'ONLINE'}])
        source = {'overall_status': 'OK', 'open_incident_count': 0,
                  'domains': {'ZFS': {'status': 'OK', 'open_incidents': 0,
                                     'last_observation': None, 'integrity': summary}}}
        for path in ('/v1/status', '/v1/domains', '/v1/domains/ZFS'):
            code, response = route(self.db, path, {}, status_builder=lambda: source)
            self.assertEqual(code, 200)
            data = response['data']
            domain = data['domains'][0] if path == '/v1/status' else data[0] if path == '/v1/domains' else data
            self.assertEqual(domain['integrity'], summary)
            self.assertEqual(domain['status'], 'OK')


if __name__ == '__main__':
    unittest.main()
