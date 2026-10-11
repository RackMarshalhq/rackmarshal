"""A successful exit alone is not hardware processor result evidence."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VALID = {'status': 'OK', 'consumer': 'hardware_incident_processor',
         'opened': 0, 'escalated': 0, 'recovered': 0, 'processed': 0,
         'open_incidents': 0, 'watermark': None, 'note': 'no_observations'}


class HardwareProcessorResultTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        conf = self.root / 'config'
        values = {'STATE_DB': self.root / 'state.db', 'SITE_NAME': 'fixture',
                  'HARDWARE_HOT_THRESHOLD_C': 80, 'HARDWARE_HOT_REQUIRED_SAMPLES': 2,
                  'HARDWARE_URGENT_THRESHOLD_C': 90, 'HARDWARE_RECOVERY_THRESHOLD_C': 70,
                  'HARDWARE_RECOVERY_REQUIRED_SAMPLES': 2, 'INSTALL_ROOT': ROOT,
                  'VENV_PYTHON': sys.executable}
        conf.write_text('\n'.join(f'{k}={v}' for k, v in values.items()))
        with patch.dict(os.environ, {'RACKMARSHAL_CONFIG': str(conf),
                                    'RACKMARSHAL_STATE_DB': str(self.root / 'state.db')}):
            spec = importlib.util.spec_from_file_location('hardware_result_fixture', ROOT / 'rackmarshal/domains/hardware/cycle.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def response(self, output, returncode=0):
        return subprocess.CompletedProcess(['fictional'], returncode, output, '')

    def invoke(self, output, returncode=0):
        with patch.object(self.module, 'run_process', return_value=self.response(output, returncode)), contextlib.redirect_stdout(io.StringIO()):
            return self.module.process_hardware_incidents_ledger()

    def test_current_processor_success_variants_accepted(self):
        for note in ('no_observations', 'already_processed', 'cursor_initialized_skip_backfill', 'observation_driven_stepG'):
            result = dict(VALID, note=note)
            if note != 'no_observations':
                result.update(watermark=5, latest_observation_id=5)
            with self.subTest(note=note):
                self.assertEqual(self.invoke(json.dumps(result)), result)

    def test_zero_exit_missing_malformed_or_extra_output_rejected(self):
        for output in ('', 'not json', '{broken}', 'null', '[]', 'true', '123',
                       'prefix\n' + json.dumps(VALID), json.dumps(VALID) + '\ntrailer',
                       json.dumps(VALID) + json.dumps(VALID)):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                self.invoke(output)

    def test_wrong_status_identity_missing_or_invalid_counts_rejected(self):
        cases = [{}, dict(VALID, status='FAILED'), dict(VALID, consumer='other')]
        for field in ('opened', 'escalated', 'recovered', 'processed', 'open_incidents'):
            absent = dict(VALID)
            absent.pop(field)
            cases.append(absent)
            cases.extend(dict(VALID, **{field: value}) for value in (-1, None, '0', True, 0.0))
        for result in cases:
            with self.subTest(result=result), self.assertRaises(RuntimeError):
                self.invoke(json.dumps(result))

    def test_nonzero_exit_rejected_despite_success_json(self):
        with self.assertRaises(SystemExit):
            self.invoke(json.dumps(VALID), returncode=1)

    def test_bad_processor_prevents_cycle_success_and_notifications(self):
        payload = {'collector': 'hardware_temperature', 'observed_at': '2026-01-01T00:00:00Z', 'devices': []}
        with patch.object(self.module, 'collect', return_value=payload), \
             patch.object(self.module, 'run_process', return_value=self.response('')), \
             patch.object(self.module, 'enqueue_notifications') as enqueue, \
             patch.object(self.module, 'deliver_notifications') as deliver, \
             patch.object(self.module, 'emit') as emit:
            with self.assertRaisesRegex(RuntimeError, 'invalid JSON'):
                self.module.main()
            enqueue.assert_not_called()
            deliver.assert_not_called()
            emit.assert_not_called()

    def test_staging_smoke_rejects_optimization_before_temporary_state(self):
        script = ROOT / 'tests/staging_smoke.py'
        code = "import runpy, tempfile; from unittest.mock import patch;\nwith patch.object(tempfile, 'TemporaryDirectory', side_effect=AssertionError('state creation attempted')):\n runpy.run_path(" + repr(str(script)) + ", run_name='__main__')"
        for flags, optimization in ((('-O',), None), (('-OO',), None), ((), '1')):
            env = dict(os.environ)
            env.pop('PYTHONOPTIMIZE', None)
            if optimization:
                env['PYTHONOPTIMIZE'] = optimization
            with self.subTest(flags=flags, optimization=optimization):
                result = subprocess.run([sys.executable, *flags, '-c', code], cwd=ROOT,
                                        env=env, text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Staging smoke requires assertions', result.stderr)
                self.assertNotIn('state creation attempted', result.stderr)
