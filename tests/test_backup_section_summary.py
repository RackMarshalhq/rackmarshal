"""Partial observer evidence must not be displayed as measured zero/healthy."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class BackupSectionSummaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        config = root / 'config'
        config.write_text(f'STATE_DB={root / "state.db"}\nSTATUS_API_LISTEN_ADDRESS=127.0.0.1\nSTATUS_API_LISTEN_PORT=9110\n')
        with patch.dict(os.environ, {'RACKMARSHAL_CONFIG': str(config)}):
            spec = importlib.util.spec_from_file_location('backup_summary_fixture', ROOT / 'rackmarshal/api/status.py')
            self.status = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.status)
        self.probe = {
            'primary': {'vm/999': {'age_hours': 2}},
            'secondary': {'vm/999': {'age_hours': 4}},
            'missing_on_secondary': [], 'observed_at': '2026-01-01T00:00:00Z',
            'phones': {'fixture': {'age_hours': 2, 'exists': True}},
            'messages': {'fixture': {'pull': {'age_hours': 1}}},
        }

    def summary(self, probe=None):
        return self.status.pbs_store_summary({'pbs_store_probe': self.probe if probe is None else probe})

    def test_primary_timeout_preserves_successful_secondary_and_messages(self):
        self.probe['section_errors'] = {'primary': {'state': 'UNKNOWN', 'reason': 'deadline_exceeded'}}
        before = copy.deepcopy(self.probe)
        result = self.summary()
        self.assertIsNone(result['primary_count'])
        self.assertEqual(result['secondary_count'], 1)
        self.assertEqual(result['max_secondary_age_hours'], 4)
        self.assertIsNone(result['missing_on_secondary'])
        self.assertEqual(result['messages'], self.probe['messages'])
        self.assertEqual(result['section_errors'], self.probe['section_errors'])
        self.assertEqual(self.probe, before)

    def test_secondary_timeout_never_exposes_stale_count_age_or_missing_list(self):
        self.probe['section_errors'] = {'secondary': {'state': 'UNKNOWN', 'reason': 'worker_busy'}}
        self.probe['missing_on_secondary'] = ['vm/1000']
        # An invalid failed-section body must not hide independent valid sections.
        self.probe['secondary'] = {'vm/999': {'age_hours': 'private-invalid-age'}}
        result = self.summary()
        self.assertEqual(result['primary_count'], 1)
        for field in ('secondary_count', 'max_secondary_age_hours', 'missing_on_secondary'):
            self.assertIsNone(result[field], field)
        self.assertEqual(result['phones']['fixture']['exists'], True)
        self.assertNotIn('private-invalid-age', json.dumps(result))

    def test_both_failed_stores_and_null_derived_lists(self):
        self.probe.update(primary={}, secondary={}, missing_on_secondary=None,
                          section_errors={key: {'state': 'UNKNOWN', 'reason': 'lock_unavailable'}
                                          for key in ('primary', 'secondary')})
        result = self.summary()
        for field in ('primary_count', 'secondary_count', 'missing_on_secondary', 'max_secondary_age_hours'):
            self.assertIsNone(result[field], field)

    def test_true_successful_empty_sections_remain_measured_zero(self):
        result = self.summary({'primary': {}, 'secondary': {}, 'missing_on_secondary': [], 'section_errors': {}})
        self.assertEqual(result['primary_count'], 0)
        self.assertEqual(result['secondary_count'], 0)
        self.assertEqual(result['missing_on_secondary'], [])
        self.assertIsNone(result['max_secondary_age_hours'])
        self.assertEqual(result['section_errors'], {})

    def test_legacy_payload_shape_and_collector_errors_unchanged(self):
        result = self.summary()
        self.assertNotIn('section_errors', result)
        self.assertEqual((result['primary_count'], result['secondary_count'], result['max_secondary_age_hours']), (1, 1, 4))
        self.assertEqual(self.summary({'_error': 'collector timeout'}),
                         {'policy': 'alert_only_when_primary_stale', 'error': 'collector timeout'})
        self.assertEqual(self.summary({})['primary_count'], 0)
        self.assertIsNone(self.status.pbs_store_summary(None))

    def test_failed_nonstore_sections_do_not_publish_stale_success(self):
        self.probe['section_errors'] = {'phones': {'state': 'UNKNOWN', 'reason': 'worker_failed'}}
        result = self.summary()
        self.assertEqual(result['phones'], {})
        self.assertEqual(result['messages'], self.probe['messages'])
        self.assertEqual((result['primary_count'], result['secondary_count']), (1, 1))

    def test_reason_and_worker_extras_are_sanitized(self):
        self.probe['section_errors'] = {'primary': {'state': 'UNKNOWN', 'reason': 'private traceback /some/path',
                                                    'command': 'private-command', 'payload': {'private': 'value'}}}
        result = self.summary()
        self.assertEqual(result['section_errors'], {'primary': {'state': 'UNKNOWN', 'reason': 'section_unavailable'}})
        self.assertIsNone(result['primary_count'])
        self.assertNotIn('private', json.dumps(result))

    def test_malformed_diagnostics_fail_honestly_without_echo_or_state_changes(self):
        bad = [None, [], 'private-details', {'private-section': {'state': 'UNKNOWN', 'reason': 'worker_failed'}},
               {'primary': None}, {'primary': []}, {'primary': {'state': 'OK', 'reason': 'worker_failed'}},
               {'primary': {'state': 'UNKNOWN'}}, {'primary': {'state': 'UNKNOWN', 'reason': 7}},
               {'primary': {'state': 'UNKNOWN', 'reason': ''}}]
        for value in bad:
            with self.subTest(value=value):
                self.probe['section_errors'] = value
                payload = {'pbs_store_probe': self.probe}
                before = copy.deepcopy(payload)
                domain = {'status': 'PROBLEM', 'open_incidents': 1}
                self.status.attach_backup_summary(domain, payload)
                self.assertEqual(domain['pbs_store']['code'], 'BACKUP_SUMMARY_UNAVAILABLE')
                self.assertEqual(domain['pbs_store']['evidence_state'], 'UNKNOWN')
                self.assertNotIn('private', json.dumps(domain))
                self.assertEqual((domain['status'], domain['open_incidents']), ('PROBLEM', 1))
                self.assertEqual(payload, before)

    def test_attach_partial_summary_keeps_successful_sections_and_incident_state(self):
        self.probe['section_errors'] = {'phones': {'state': 'UNKNOWN', 'reason': 'deadline_exceeded'}}
        domain = {'status': 'PROBLEM', 'open_incidents': 1}
        self.status.attach_backup_summary(domain, {'pbs_store_probe': self.probe})
        self.assertEqual(domain['phones'], {})
        self.assertEqual(domain['messages'], self.probe['messages'])
        self.assertEqual(domain['pbs_store']['section_errors'], self.probe['section_errors'])
        self.assertEqual((domain['status'], domain['open_incidents']), ('PROBLEM', 1))


if __name__ == '__main__':
    unittest.main()
