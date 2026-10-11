"""Recorded evidence and invalid freshness policy remain distinguishable."""
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from rackmarshal.selfwatch.incidents import evaluate_self_signals
from rackmarshal.ui.dashboard import render_collection_coverage

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
OBS = {'PVE': {'observed_at': '2026-01-01T11:59:00Z'}}


class StatusDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.plugins = self.root / 'domains'
        self.plugins.mkdir()
        config = self.root / 'config'
        config.write_text(f'STATE_DB={self.root / "state.db"}\nDOMAINS_DIR={self.plugins}\nSTATUS_API_LISTEN_ADDRESS=127.0.0.1\nSTATUS_API_LISTEN_PORT=9110\n')
        self.env = {'RACKMARSHAL_CONFIG': str(config)}
        with patch.dict(os.environ, self.env):
            spec = importlib.util.spec_from_file_location('status_diagnostics_fixture', ROOT / 'rackmarshal/api/status.py')
            self.status = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.status)

    def plugin(self, body):
        path = self.plugins / 'pve' / 'plugin.toml'
        path.parent.mkdir(exist_ok=True)
        path.write_text(body)
        return path

    def test_valid_policy_and_documented_default_keep_original_shape(self):
        expected = {'age_seconds': 60, 'stale_after_seconds': 900,
                    'state': 'OK', 'observed_at': OBS['PVE']['observed_at']}
        self.assertEqual(self.status.build_freshness(OBS, NOW)['PVE'], expected)
        with patch.object(self.status, 'domains_dir', return_value=self.root / 'absent-domains'):
            self.assertEqual(self.status.build_freshness(OBS, NOW)['PVE'], expected)
        self.plugin('id="pve"\n[status]\nstale_after_seconds=30\n')
        actual = self.status.build_freshness(OBS, NOW)['PVE']
        self.assertEqual(actual, dict(expected, stale_after_seconds=30, state='STALE'))
        self.plugin('id="pve"\n[status]\nstale_after_seconds="120"\n')
        self.assertEqual(self.status.build_freshness(OBS, NOW)['PVE'], dict(expected, stale_after_seconds=120))

    def test_invalid_policy_keeps_time_but_cannot_claim_freshness(self):
        for body in ('secret-invalid-toml', 'id="pve"\nstatus="secret-invalid-shape"',
                     'id="wrong-domain"', 'id="ha"', 'id=false', 'id=""',
                     *('id="pve"\n[status]\nstale_after_seconds=' + value
                       for value in ('"secret-invalid"', '-1', '0', 'true', '1.5', '[]'))):
            with self.subTest(body=body):
                self.plugin(body)
                row = self.status.build_freshness(OBS, NOW)['PVE']
                self.assertEqual(row['state'], 'MISSING')
                self.assertEqual(row['reason'], 'FRESHNESS_POLICY_UNAVAILABLE')
                self.assertEqual(row['observed_at'], OBS['PVE']['observed_at'])
                self.assertEqual(row['age_seconds'], 60)
                self.assertIsNone(row['stale_after_seconds'])
                self.assertFalse(row['threshold_configuration']['fallback_used_for_classification'])
                self.assertNotIn('secret', json.dumps(row))
                self.assertNotIn(str(self.root), json.dumps(row))
                self.assertEqual(self.status.self_watch_status_from_parts({'PVE': row}, {}, {}), 'DEGRADED')

    def test_unreadable_metadata_reported_without_exception_contents(self):
        path = self.plugin('id="pve"')
        original = Path.read_text
        def read(candidate, *args, **kwargs):
            if candidate == path:
                raise PermissionError('sensitive path or data')
            return original(candidate, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            row = self.status.build_freshness(OBS, NOW)['PVE']
        self.assertEqual(row['threshold_configuration']['code'], 'PLUGIN_METADATA_UNREADABLE')
        self.assertNotIn('sensitive', json.dumps(row))

    def test_bad_policy_preserves_open_freshness_signal_and_reason(self):
        self.plugin('id="pve"\n[status]\nstale_after_seconds=false')
        freshness = self.status.build_freshness(OBS, NOW)
        desired = evaluate_self_signals({'PVE': freshness['PVE']}, {}, {})
        self.assertEqual(desired[0]['signal_key'], 'freshness:PVE')
        self.assertEqual(desired[0]['detail']['reason'], 'FRESHNESS_POLICY_UNAVAILABLE')
        with patch.dict(os.environ, self.env):
            spec = importlib.util.spec_from_file_location('selfwatch_diagnostics_fixture', ROOT / 'rackmarshal/selfwatch/cycle.py')
            cycle = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cycle)
        with closing(sqlite3.connect(':memory:')) as db:
            db.row_factory = sqlite3.Row
            db.executescript((ROOT / 'rackmarshal/db/migrations/005_notify_self.sql').read_text())
            cycle.sync_self_incidents(db, evaluate_self_signals({'PVE': {'state': 'STALE'}}, {}, {}))
            result = cycle.sync_self_incidents(db, desired)
            row = db.execute('SELECT * FROM self_incidents').fetchone()
            self.assertEqual(result['recovered'], 0)
            self.assertEqual(row['incident_state'], 'OPEN')
            self.assertIsNone(row['recovered_at'])
            self.assertEqual(json.loads(row['detail_json'])['reason'], 'FRESHNESS_POLICY_UNAVAILABLE')

    def test_dashboard_reports_policy_gap_and_preserves_observation_time(self):
        self.plugin('invalid metadata')
        with closing(sqlite3.connect(':memory:')) as db:
            db.row_factory = sqlite3.Row
            db.execute('CREATE TABLE observations(id INTEGER, observed_at TEXT, collector TEXT)')
            db.execute('INSERT INTO observations VALUES(1, ?, ?)', (OBS['PVE']['observed_at'], 'pve_cluster_resources'))
            page = render_collection_coverage(db, freshness_builder=self.status.build_freshness, domain='PVE')
        self.assertIn('Freshness policy unavailable', page)
        self.assertNotIn('Fresh observation</strong>', page)
        self.assertNotIn('No usable observation time', page)
        self.assertNotIn('Stale after 900', page)
        self.assertIn('2026-01-01', page)

    def test_summary_derivation_failure_is_explicit_and_sanitized(self):
        for payload in ({'pbs_store_probe': {'secondary': {'fixture': {'age_hours': 'private-value'}}}},
                        {'pbs_store_probe': {'phones': 'private-value'}}):
            with self.subTest(payload=payload):
                domain = {'status': 'OK', 'open_incidents': 0}
                self.status.attach_backup_summary(domain, payload)
                self.assertEqual(domain['pbs_store']['evidence_state'], 'UNKNOWN')
                self.assertEqual(domain['pbs_store']['code'], 'BACKUP_SUMMARY_UNAVAILABLE')
                self.assertEqual(domain['status'], 'OK')
                self.assertNotIn('private-value', json.dumps(domain))
                self.assertNotIn('messages', domain)

    def test_valid_and_absent_backup_summaries_preserve_behavior(self):
        for payload in (None, {}, {'other': {}}):
            domain = {'status': 'OK'}
            self.status.attach_backup_summary(domain, payload)
            self.assertEqual(domain, {'status': 'OK'})
        payload = {'pbs_store_probe': {'messages': {'fixture': {'exists': True}}}}
        domain = {}
        self.status.attach_backup_summary(domain, payload)
        self.assertEqual(domain['messages'], payload['pbs_store_probe']['messages'])
        self.assertEqual(domain['pbs_store'], self.status.pbs_store_summary(payload))
        domain = {}
        self.status.attach_backup_summary(domain, {'pbs_store_probe': {'_error': 'collector timeout'}})
        self.assertEqual(domain['pbs_store']['error'], 'collector timeout')
