"""Finite stage execution never turns timeout/partial output into success."""
import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

from rackmarshal import process

ROOT = Path(__file__).resolve().parents[1]


class ProcessTimeoutTests(unittest.TestCase):
    def test_success_bytes_text_input_and_nonzero(self):
        command = [sys.executable, '-c', 'import sys;sys.stdout.write(sys.stdin.read().upper())']
        result = process.run(command, input='hello', text=True, capture_output=True, timeout=5)
        self.assertEqual((result.stdout, result.returncode), ('HELLO', 0))
        result = process.run(command, input=b'hello', capture_output=True, timeout=5, env=None)
        self.assertEqual(result.stdout, b'HELLO')
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            process.run([sys.executable, '-c', 'raise SystemExit(4)'], check=True, timeout=5)
        self.assertEqual(caught.exception.returncode, 4)

    def test_timeout_kills_shell_and_grandchild_holding_output_pipe(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / 'child.pid'
            code = 'import os,time,pathlib;pathlib.Path(' + repr(str(pidfile)) + ').write_text(str(os.getpid()));time.sleep(60)'
            # Background child retains stdout/stderr while bash waits indefinitely.
            shell = ["bash", "-c", '"$1" -c "$2" & wait', '_', sys.executable, code]
            started = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                process.run(shell, timeout=0.5, capture_output=True)
            self.assertLess(time.monotonic() - started, 5)
            self.assertTrue(pidfile.exists(), 'fixture child must actually have started')
            pid = int(pidfile.read_text())
            status = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True, timeout=5)
            self.assertTrue(status.returncode != 0 or status.stdout.strip().startswith('Z'), status.stdout)
            self.assertIsNone(caught.exception.output)
            self.assertIsNone(caught.exception.stderr)
            self.assertNotIn(code, str(caught.exception))

    def test_nested_outer_and_inner_timeouts_kill_shared_group(self):
        for outer_timeout, inner_timeout in ((0.5, 10), (5, 0.2)):
            with self.subTest(outer=outer_timeout), tempfile.TemporaryDirectory() as directory:
                pidfile = Path(directory) / 'nested.pid'
                leaf = 'import os,time,pathlib;pathlib.Path(' + repr(str(pidfile)) + ').write_text(str(os.getpid()));time.sleep(60)'
                middle = ('from rackmarshal.process import run;import sys;run([sys.executable,"-c",' + repr(leaf)
                          + '],timeout=' + str(inner_timeout) + ',capture_output=True,env={"PATH":"/usr/bin:/bin"});print("unexpected success")')
                started = time.monotonic()
                if outer_timeout < inner_timeout:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        process.run([sys.executable, '-c', middle], timeout=outer_timeout, capture_output=True)
                else:
                    result = process.run([sys.executable, '-c', middle], timeout=outer_timeout, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn(b'unexpected success', result.stdout)
                self.assertLess(time.monotonic() - started, 4)
                self.assertTrue(pidfile.exists())
                status = subprocess.run(['ps', '-p', pidfile.read_text(), '-o', 'stat='], capture_output=True, text=True, timeout=5)
                self.assertTrue(status.returncode != 0 or status.stdout.strip().startswith('Z'), status.stdout)

    def test_invalid_or_same_session_marker_never_targets_caller_group(self):
        own_group = os.getpgrp()
        for owner, session in (('999999999', '999999999'), (str(os.getppid()), str(os.getsid(0))), ('bad', 'bad'), ('9' * 100, '1')):
            with patch.dict(os.environ, {process._OWNER_PID: owner, process._OWNER_SESSION: session}):
                self.assertIsNone(process._managed_group())
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.run([sys.executable, '-c', 'import time;time.sleep(60)'], timeout=0.1)
                self.assertEqual(os.getpgrp(), own_group)

    def test_partial_success_output_is_not_accepted_or_committed_writes_undone(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'state.db'
            code = ('import sqlite3,time; c=sqlite3.connect(' + repr(str(database)) + ');'
                    'c.execute("CREATE TABLE evidence(value TEXT)");'
                    'c.execute("INSERT INTO evidence VALUES (\'retained\')");c.commit();'
                    'print(\'{"status":"OK"}\',flush=True);time.sleep(60)')
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                process.run([sys.executable, '-c', code], timeout=0.5, capture_output=True, text=True)
            self.assertIsNone(caught.exception.output)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('SELECT value FROM evidence').fetchall(), [('retained',)])
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_timeout_errors_redact_command_and_captured_output(self):
        code = 'import time,sys;print("synthetic-private-output",flush=True);print("synthetic-private-error",file=sys.stderr,flush=True);time.sleep(60)'
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            process.run([sys.executable, '-c', code, 'synthetic-private-argument'], timeout=0.2, capture_output=True)
        self.assertEqual(caught.exception.cmd, 'local command')
        self.assertEqual(caught.exception.timeout, 0.2)
        self.assertIsNone(caught.exception.output)
        self.assertIsNone(caught.exception.stderr)
        self.assertNotIn('synthetic-private', str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_stage_override_requires_positive_finite_value(self):
        with patch.dict(os.environ, {'RACKMARSHAL_STAGE_TIMEOUT_SECONDS': '900'}):
            self.assertEqual(process.stage_timeout(), 900)
        for value in ('0', '-1', 'nan', 'inf', 'invalid'):
            with self.subTest(value=value), patch.dict(os.environ, {'RACKMARSHAL_STAGE_TIMEOUT_SECONDS': value}):
                with self.assertRaises(ValueError):
                    process.stage_timeout()
        with patch('subprocess.Popen') as spawn:
            for value in (0, -1, float('nan'), float('inf')):
                with self.assertRaises(ValueError):
                    process.run(['unused'], timeout=value)
            spawn.assert_not_called()

    def load_module(self, relative, root):
        config = root / 'config'
        values = {'STATE_DB': root / 'state.db', 'SITE_NAME': 'fixture', 'PVE_NODE': 'fixture',
                  'HARDWARE_HOT_THRESHOLD_C': 80, 'HARDWARE_HOT_REQUIRED_SAMPLES': 2,
                  'HARDWARE_URGENT_THRESHOLD_C': 90, 'HARDWARE_RECOVERY_THRESHOLD_C': 70,
                  'HARDWARE_RECOVERY_REQUIRED_SAMPLES': 2, 'INSTALL_ROOT': ROOT, 'VENV_PYTHON': sys.executable, 'STATUS_API_LISTEN_ADDRESS': '127.0.0.1', 'STATUS_API_LISTEN_PORT': '9110'}
        config.write_text('\n'.join(f'{key}={value}' for key, value in values.items()))
        with patch.dict(os.environ, {'RACKMARSHAL_CONFIG': str(config), 'RACKMARSHAL_STATE_DB': str(root / 'state.db')}):
            spec = importlib.util.spec_from_file_location('timeout_fixture', ROOT / relative)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_credential_shell_timeout_returns_typed_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential = root / 'synthetic.env'
            credential.write_text('sleep 60\nHA_URL=http://localhost\nHA_TOKEN=synthetic\n')
            cases = [('rackmarshal/notifications/delivery.py', 'load_ha_credentials', 'DeliveryError'),
                     ('rackmarshal/domains/ha/collector.py', 'load_credentials', 'CollectorError')]
            for path, function, error in cases:
                module = self.load_module(path, root)
                with patch.object(module, 'CREDENTIAL_TIMEOUT_SECONDS', 0.2), patch.object(module, 'CREDENTIAL', str(credential), create=True):
                    with self.assertRaises(getattr(module, error)) as caught:
                        getattr(module, function)(str(credential)) if function == 'load_ha_credentials' else getattr(module, function)()
                    self.assertIn('stage incomplete', str(caught.exception))
                    self.assertNotIn(str(credential), str(caught.exception))
                    self.assertTrue(caught.exception.__suppress_context__)

    def test_cycle_wrappers_reject_partial_json_after_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, function in [('domains/pve/cycle.py', 'run_json'), ('domains/ha/cycle.py', 'run'),
                                       ('domains/backup/cycle.py', 'run'), ('domains/zfs/cycle.py', 'run'),
                                       ('domains/hardware/cycle.py', 'run_json'), ('selfwatch/cycle.py', 'run_json')]:
                with self.subTest(relative=relative):
                    module = self.load_module('rackmarshal/' + relative, root)
                    with patch.object(module, 'stage_timeout', return_value=0.15):
                        with self.assertRaisesRegex(Exception, 'stage incomplete'):
                            getattr(module, function)([sys.executable, '-c', 'import time;print(\'{"status":"OK"}\',flush=True);time.sleep(60)'])

    def test_managed_parent_survives_backup_soft_probe_timeout(self):
        code = textwrap.dedent("""
            import json, subprocess, sys
            from unittest.mock import patch
            with patch('rackmarshal.core.config.load_config', return_value={'PVE_NODE':'fixture'}):
                from rackmarshal.domains.backup import collector
            original_run = subprocess.run
            def local_sleep(command, **kwargs):
                if command[0] != '/usr/bin/ssh' or kwargs['timeout'] != 30:
                    raise RuntimeError('unexpected probe contract')
                return original_run([sys.executable, '-c', 'import time;time.sleep(60)'],
                                    text=True, capture_output=True, timeout=0.1)
            with patch.object(collector, '_backup_conf', return_value='synthetic'), patch.object(collector.subprocess, 'run', side_effect=local_sleep):
                probe = collector.fetch_pbs_store_probe()
            print(json.dumps({'continued':True,'probe':probe}))
        """)
        result = process.run([sys.executable, '-c', code], timeout=5, capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertTrue(report['continued'])
        self.assertIn('timed out', report['probe']['_error'])
        self.assertNotIn('recovered', report['probe'])

    def test_managed_parent_retains_explainer_timeout_and_deterministic_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            explainer = Path(directory) / 'synthetic-explainer'
            explainer.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(60)\n')
            explainer.chmod(0o700)
            code = textwrap.dedent("""
                import json, sys
                from unittest.mock import patch
                from rackmarshal.notifications import delivery
                try:
                    delivery.run_explainer(sys.argv[1], {'synthetic':'incident'}, timeout_seconds=0.1)
                except delivery.DeliveryError as exc:
                    error = str(exc)
                else:
                    raise RuntimeError('expected explainer timeout')
                row = {'explanation_json':json.dumps({'mode':'FALLBACK','explainer_succeeded':False})}
                with patch.object(delivery, 'local_ai_enabled', return_value=True), patch.object(delivery, 'local_ai_attach_to_notify', return_value=True):
                    record, message = delivery.resolve_opened_explanation_and_message(row, 'synthetic deterministic facts')
                print(json.dumps({'continued':True,'error':error,'record':record,'message':message}))
            """)
            result = process.run([sys.executable, '-c', code, str(explainer)], timeout=5, capture_output=True, text=True, check=True)
            report = json.loads(result.stdout)
            self.assertTrue(report['continued'])
            self.assertIn('explainer timed out', report['error'])
            self.assertEqual(report['record']['mode'], 'FALLBACK')
            self.assertEqual(report['message'], 'synthetic deterministic facts')

    def test_comparator_timeout_cannot_recover_retained_incident(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = self.load_module('rackmarshal/domains/pve/incidents.py', root)
            with closing(sqlite3.connect(root / 'state.db')) as conn:
                conn.execute("CREATE TABLE resource_incidents(id INTEGER,incident_state TEXT)")
                conn.execute("INSERT INTO resource_incidents VALUES(1,'OPEN')")
                conn.commit()
            command = [sys.executable, '-c', 'import time;print(\'{"schema_version":1,"differences":[]}\',flush=True);time.sleep(60)']
            with patch.object(module, 'preflight_processing_order', return_value=None), patch.object(module, 'COMPARATOR', command), patch.object(module, 'LOCAL_STAGE_TIMEOUT_SECONDS', 0.2):
                with self.assertRaises(module.IncidentProcessorError):
                    module.process(2)
            with closing(sqlite3.connect(root / 'state.db')) as conn:
                self.assertEqual(conn.execute('SELECT incident_state FROM resource_incidents').fetchall(), [('OPEN',)])

    def test_packet_builder_timeout_is_enqueue_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            module = self.load_module('rackmarshal/notifications/queue.py', Path(directory))
            with patch.object(module, 'LOCAL_STAGE_TIMEOUT_SECONDS', 0.15):
                with self.assertRaises(module.EnqueueError):
                    module.build_packet([sys.executable, '-c', 'import time;time.sleep(60)'], 'unused', 'HA', 1, 'OPEN')


if __name__ == '__main__':
    unittest.main()
