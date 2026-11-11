"""Upgrade transactions that also change the database: crash recovery at every phase."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rackmarshal.maintenance import migration_rehearsal as mr
from rackmarshal.maintenance.lifecycle import Lifecycle, Refused, database_snapshot, inventory

PHASES = ('STAGING', 'STAGED', 'GUARD_INTENT', 'GUARDED', 'QUIESCED', 'OLD_RENAME_INTENT', 'OLD_RETAINED',
          'ACTIVATED', 'MIGRATE_INTENT', 'MIGRATED', 'ACCEPTED', 'RESUME_AUTHORIZED')
SQL = "CREATE TABLE extra(id INTEGER PRIMARY KEY, v TEXT);\nALTER TABLE incidents ADD COLUMN note TEXT;\n"


def setUpModule():
    global _umask
    _umask = os.umask(0o022)


def tearDownModule():
    os.umask(_umask)


class Runtime:
    def __init__(self):
        self.calls = []
        self.fail_accept = False

    def snapshot(self): return {'active': ['status'], 'enabled': []}
    def guard(self, *a): self.calls.append('guard')
    def quiesce(self, *a): self.calls.append('quiesce')

    def accept(self, *a):
        self.calls.append('accept')
        if self.fail_accept:
            raise RuntimeError('acceptance failed')

    def resume(self, tx, snap, authorize): authorize(); self.calls.append('resume')
    def hold(self, *a): self.calls.append('hold')


class MigrationTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.active, self.candidate, self.store = root / 'active', root / 'candidate', root / 'store'
        for p in (self.active, self.candidate, self.store):
            p.mkdir(mode=0o700)
        (self.active / 'app.py').write_text('old')
        (self.candidate / 'app.py').write_text('new')
        self.conf = root / 'config'
        self.conf.write_text('secret')
        self.conf.chmod(0o600)
        self.db = root / 'state.sqlite'
        with closing(sqlite3.connect(self.db)) as c, c:
            c.executescript("CREATE TABLE schema_migrations(id TEXT PRIMARY KEY, checksum TEXT);"
                            "INSERT INTO schema_migrations VALUES('001','abc');"
                            "CREATE TABLE incidents(id INTEGER PRIMARY KEY, state TEXT);"
                            "INSERT INTO incidents VALUES(1,'OPEN');")
        self.rt = Runtime()
        self.engine = Lifecycle(self.active, self.store, self.db, [self.conf], self.rt)
        self.before = inventory(self.active, os.getuid())
        self.schema = database_snapshot(self.db)
        self.migration = self.describe(SQL)

    def describe(self, sql, wrong_expectation=False):
        sha = hashlib.sha256(sql.encode()).hexdigest()
        result = mr.rehearse(self.db, [('002_extra', sql, sha)]) if not wrong_expectation else {
            'schema_sha256': '0' * 64, 'ledger': []}
        return {'migrations': [('002_extra', sql, sha)], 'expected_schema_sha256': result['schema_sha256'],
                'expected_ledger': result['ledger']}

    def apply(self, migration=None):
        return self.engine.upgrade(self.candidate, {'version': 'fixture'}, self.before, self.schema, True,
                                   migration=migration or self.migration)

    def pending(self):
        return next(p for p in self.store.glob('transaction-*')
                    if json.loads((p / 'transaction.json').read_text())['phase'] != 'ROLLED_BACK')

    def incidents(self):
        with closing(sqlite3.connect(self.db)) as c:
            return c.execute("SELECT id,state FROM incidents").fetchall()

    def tables(self):
        with closing(sqlite3.connect(self.db)) as c:
            return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def test_migrating_upgrade_commits_and_changes_database(self):
        tx = self.apply()
        self.assertEqual(json.loads((tx / 'transaction.json').read_text())['phase'], 'COMMITTED')
        self.assertIn('extra', self.tables())
        self.assertEqual(self.incidents(), [(1, 'OPEN')])
        self.assertEqual([r[0] for r in database_snapshot(self.db)['ledger']], ['001', '002_extra'])
        self.assertEqual((self.active / 'app.py').read_text(), 'new')

    def test_rollback_after_commit_restores_code_and_keeps_migrated_database(self):
        tx = self.apply()
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("INSERT INTO incidents(id,state) VALUES(2,'NEWER')")
        newer = database_snapshot(self.db)
        self.engine.rollback(tx, True)
        self.assertEqual((self.active / 'app.py').read_text(), 'old')
        self.assertEqual(database_snapshot(self.db), newer)
        self.assertIn('extra', self.tables())

    def test_interruption_at_every_phase_recovers_old_code_and_all_data(self):
        for phase in PHASES:
            with self.subTest(phase=phase):
                def interrupt(value, phase=phase):
                    if value == phase:
                        raise KeyboardInterrupt(phase)
                self.engine.fault = interrupt
                with self.assertRaises(KeyboardInterrupt):
                    self.apply()
                self.engine.fault = lambda p: None
                self.engine.rollback(self.pending(), True)
                self.assertEqual(inventory(self.active, os.getuid()), self.before)
                self.assertEqual(self.incidents(), [(1, 'OPEN')])
                # Whether the migration happened or not, the database is wholly old or wholly new.
                after = database_snapshot(self.db)
                self.assertIn(after['ledger'], ([('001', 'abc')], [('001', 'abc'), ('002_extra', self.migration['migrations'][0][2])]))
                self.assertEqual(('extra' in self.tables()), len(after['ledger']) == 2)
                self.rebuild_fixture()

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_process_exit_during_migration_recovers(self):
        for phase in ('MIGRATE_INTENT', 'MIGRATED'):
            with self.subTest(phase=phase):
                pid = os.fork()
                if pid == 0:
                    self.engine.fault = lambda p: os._exit(77) if p == phase else None
                    try:
                        self.apply()
                    except BaseException:
                        os._exit(78)
                    os._exit(79)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 77)
                self.engine.rollback(self.pending(), True)
                self.assertEqual(inventory(self.active, os.getuid()), self.before)
                self.assertEqual(self.incidents(), [(1, 'OPEN')])
                self.rebuild_fixture()

    def rebuild_fixture(self):
        """Reset code, database and store between sub-tests."""
        import shutil
        shutil.rmtree(self.store)
        self.store.mkdir(mode=0o700)
        with closing(sqlite3.connect(self.db)) as c, c:
            c.executescript("DROP TABLE IF EXISTS extra;DELETE FROM schema_migrations WHERE id!='001';")
            cols = [r[1] for r in c.execute("PRAGMA table_info(incidents)")]
            if 'note' in cols:
                c.executescript("ALTER TABLE incidents DROP COLUMN note;")
        self.schema = database_snapshot(self.db)
        self.migration = self.describe(SQL)

    def test_failing_migration_is_caught_on_the_backup_before_any_change(self):
        sql = "CREATE TABLE ok2(x);\nINSERT INTO nowhere VALUES(1);\n"
        bad = dict(self.migration, migrations=[('002_extra', sql, hashlib.sha256(sql.encode()).hexdigest())])
        with self.assertRaises(mr.RehearsalError):
            self.apply(bad)
        self.assertEqual(database_snapshot(self.db), self.schema)
        self.assertEqual((self.active / 'app.py').read_text(), 'old')
        tx = self.pending()
        self.assertEqual(json.loads((tx / 'transaction.json').read_text())['phase'], 'RECOVERY_REQUIRED')
        self.engine.rollback(tx, True)

    def test_plan_that_differs_from_quiesced_rehearsal_is_refused_before_any_change(self):
        with self.assertRaises(Refused):
            self.apply(self.describe(SQL, wrong_expectation=True))
        self.assertEqual(database_snapshot(self.db), self.schema)
        self.assertEqual((self.active / 'app.py').read_text(), 'old')
        self.assertEqual(self.rt.calls[-1], 'hold')

    def test_migration_that_loses_rows_is_refused_on_the_quiesced_data(self):
        sql = "DELETE FROM incidents;\n"
        described = self.describe(sql)  # the plan was made while the data looked harmless to the planner
        described = dict(described, migrations=[('002_extra', sql, hashlib.sha256(sql.encode()).hexdigest())])
        with self.assertRaises(Refused):
            self.apply(described)
        self.assertEqual(self.incidents(), [(1, 'OPEN')])

    def test_failed_acceptance_after_migration_rolls_back_code_and_keeps_new_schema(self):
        self.rt.fail_accept = True
        with self.assertRaises(RuntimeError):
            self.apply()
        self.rt.fail_accept = False
        self.engine.rollback(self.pending(), True)
        self.assertEqual((self.active / 'app.py').read_text(), 'old')
        self.assertIn('extra', self.tables())

    def test_bad_descriptions_are_refused_before_anything_happens(self):
        bad_checksum = dict(self.migration, migrations=[('002_extra', SQL, '0' * 64)])
        already = dict(self.migration, migrations=[('001', SQL, hashlib.sha256(SQL.encode()).hexdigest())])
        for description in (bad_checksum, already, {'migrations': []}):
            with self.assertRaises(Refused):
                self.apply(description)
        self.assertEqual(self.rt.calls, [])
        self.assertEqual(list(self.store.glob('transaction-*')), [])

    def test_other_database_change_after_migration_still_refuses_rollback(self):
        tx = self.apply()
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("CREATE TABLE stranger(x)")
        with self.assertRaises(Refused):
            self.engine.rollback(tx, True)

    def test_upgrade_without_migration_still_refuses_a_changed_schema(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("CREATE TABLE stranger(x)")
        with self.assertRaises(Refused):
            self.engine.upgrade(self.candidate, {}, self.before, self.schema, True)


if __name__ == '__main__':
    unittest.main()
