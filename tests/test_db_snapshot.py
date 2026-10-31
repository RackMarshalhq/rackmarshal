"""Database snapshots: disposable databases only."""
from contextlib import closing
import fcntl
import importlib.util
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
from rackmarshal.maintenance import snapshot


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / 'state.db'
        self.out = self.root / 'snaps'
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('CREATE TABLE t(x)')
            c.executemany('INSERT INTO t VALUES(?)', [(i,) for i in range(100)])
            c.commit()

    def names(self):
        return sorted(p.name for p in self.out.iterdir())

    def test_snapshot_is_a_complete_readable_copy_and_latest_matches(self):
        dest = snapshot.create_snapshot(self.db, self.out)
        for path in (dest, self.out / 'state.db.latest'):
            with closing(sqlite3.connect(path)) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM t').fetchone()[0], 100)
                self.assertEqual(c.execute('PRAGMA quick_check').fetchall(), [('ok',)])
        self.assertEqual(oct(dest.stat().st_mode & 0o777), '0o640')
        self.assertEqual(oct(self.out.stat().st_mode & 0o777), '0o750')

    def test_source_database_is_not_modified(self):
        before = self.db.read_bytes()
        snapshot.create_snapshot(self.db, self.out)
        self.assertEqual(self.db.read_bytes(), before)

    def test_retention_keeps_the_newest_and_ignores_other_files(self):
        self.out.mkdir()
        (self.out / 'notes.txt').write_text('keep me')
        victim = self.root / 'victim'
        victim.write_text('outside')
        (self.out / 'state.db.20200101-000000Z').symlink_to(victim)
        for _ in range(4):
            snapshot.create_snapshot(self.db, self.out, retention=2)
        regular = [n for n in self.names() if re.fullmatch(r'state\.db\.\d{8}-\d{6}-\d{6}Z', n)]
        self.assertEqual(len(regular), 2)
        self.assertIn('notes.txt', self.names())
        self.assertIn('state.db.latest', self.names())
        self.assertTrue(victim.exists())
        self.assertTrue((self.out / 'state.db.20200101-000000Z').is_symlink())

    def test_bad_arguments_are_refused(self):
        with self.assertRaises(FileNotFoundError):
            snapshot.create_snapshot(self.root / 'missing.db', self.out)
        with self.assertRaises(ValueError):
            snapshot.create_snapshot(self.db, self.out, retention=0)
        self.assertFalse(self.out.exists() and any(p for p in self.out.iterdir() if p.name != '.snapshot.lock'))

    def test_a_second_run_cannot_overlap(self):
        self.out.mkdir()
        with (self.out / '.snapshot.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaises(BlockingIOError):
                snapshot.create_snapshot(self.db, self.out)

    def test_a_corrupt_source_leaves_no_snapshot_or_temporary_files(self):
        self.db.write_bytes(b'this is not a database' * 200)
        with self.assertRaises(sqlite3.DatabaseError):
            snapshot.create_snapshot(self.db, self.out)
        self.assertEqual([n for n in self.names() if n != '.snapshot.lock'], [])

    def test_a_failed_integrity_check_leaves_no_snapshot(self):
        with mock.patch.object(snapshot, '_quick_check', return_value=[('row 1 missing from index',)]):
            with self.assertRaisesRegex(RuntimeError, 'integrity'):
                snapshot.create_snapshot(self.db, self.out)
        self.assertEqual([n for n in self.names() if n != '.snapshot.lock'], [])

    def test_a_slow_snapshot_is_stopped_at_the_time_limit(self):
        ticks = iter([0.0, 1000.0, 1000.0, 1000.0, 1000.0])
        with mock.patch.object(snapshot.time, 'monotonic', lambda: next(ticks, 1000.0)):
            with self.assertRaises(TimeoutError):
                snapshot.create_snapshot(self.db, self.out)
        self.assertEqual([n for n in self.names() if n != '.snapshot.lock'], [])

    def test_not_enough_free_space_is_refused_before_copying(self):
        usage = mock.Mock(free=1024)
        with mock.patch.object(snapshot.shutil, 'disk_usage', return_value=usage):
            with self.assertRaisesRegex(OSError, 'not enough free space'):
                snapshot.create_snapshot(self.db, self.out)
        self.assertEqual([n for n in self.names() if n != '.snapshot.lock'], [])

    def test_command_line_uses_environment_defaults(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT), RACKMARSHAL_STATE_DB=str(self.db),
                   RACKMARSHAL_DB_SNAPSHOT_DIR=str(self.out), RACKMARSHAL_DB_SNAPSHOT_RETENTION='3')
        result = subprocess.run([sys.executable, '-B', '-m', 'rackmarshal.maintenance.snapshot'], capture_output=True, text=True, env=env, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RACKMARSHAL_DB_SNAPSHOT_OK path=', result.stdout)

    def test_command_line_falls_back_to_the_configuration(self):
        conf = self.root / 'conf'
        conf.write_text('STATE_DB=%s\nSTATE_DIR=%s\nSITE_NAME=fixture\n' % (self.db, self.root))
        env = {k: v for k, v in os.environ.items() if not k.startswith('RACKMARSHAL_')}
        env.update(PYTHONPATH=str(ROOT), RACKMARSHAL_CONFIG=str(conf))
        result = subprocess.run([sys.executable, '-B', '-m', 'rackmarshal.maintenance.snapshot'], capture_output=True, text=True, env=env, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'db-snapshots' / 'state.db.latest').is_file())


class PackagedUnitTests(unittest.TestCase):
    def units(self):
        return sorted((ROOT / 'packaging/systemd').glob('*.service'))

    def test_every_packaged_service_runs_a_module_that_exists(self):
        found = 0
        for unit in self.units():
            for line in unit.read_text().splitlines():
                m = re.match(r'ExecStart=\S*python\S*\s+-m\s+(\S+)', line)
                if m:
                    found += 1
                    for module in ([m.group(1).replace('%i', d) for d in ('pve', 'zfs', 'backup', 'ha', 'hardware', 'mount')] if '%i' in m.group(1) else [m.group(1)]):
                        self.assertIsNotNone(importlib.util.find_spec(module), '%s runs a module that does not exist: %s' % (unit.name, module))
        self.assertGreaterEqual(found, 4)

    def test_snapshot_units_are_packaged_installed_and_removed(self):
        spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'scripts/bootstrap-wheel.py')
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        for name in ('rackmarshal-db-snapshot.service', 'rackmarshal-db-snapshot.timer'):
            self.assertIn(name, bootstrap.UNITS)
            self.assertTrue((ROOT / 'packaging/systemd' / name).is_file())
            self.assertIn(name, (ROOT / 'scripts/install.sh').read_text())
            self.assertIn(name, (ROOT / 'scripts/uninstall.sh').read_text())
        self.assertIn('rackmarshal-db-snapshot.timer', (ROOT / 'scripts/install.sh').read_text().split('enable --now')[1])


if __name__ == '__main__':
    unittest.main()
