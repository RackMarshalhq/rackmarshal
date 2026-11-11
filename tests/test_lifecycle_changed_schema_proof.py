"""The program we could go back to must run on the database a later release leaves behind."""
from contextlib import closing
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import venv

from rackmarshal.maintenance import lifecycle_semantics as P
from rackmarshal.maintenance import migration_rehearsal as mr

ROOT = Path(__file__).resolve().parents[1]
ADD = "CREATE TABLE later_feature(id INTEGER PRIMARY KEY, v TEXT);\nALTER TABLE zfs_incidents ADD COLUMN later_note TEXT;\n"
BREAK = "ALTER TABLE zfs_observations RENAME TO zfs_observations_gone;\n"


class ChangedSchemaProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        target = cls.root / 'venv'
        venv.EnvBuilder(with_pip=False).create(target)
        site = next(target.glob('lib/python*/site-packages'))
        shutil.copytree(ROOT / 'rackmarshal', site / 'rackmarshal', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        cls.python = target / 'bin/python'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def steps(self, sql):
        return [('900_later', sql, hashlib.sha256(sql.encode()).hexdigest())]

    def test_old_program_passes_full_suite_on_additive_schema_change(self):
        work = self.root / 'additive'
        work.mkdir()
        result = P.proof(self.python, work, extra_migrations=self.steps(ADD))
        self.assertEqual(result['result'], 'FIXTURE_ASSERTIONS_PASS')
        self.assertEqual(result['extra_migrations'], ['900_later'])
        with closing(sqlite3.connect(work / 'fixture.db')) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM schema_migrations WHERE id='900_later'").fetchone()[0], 1)

    def test_old_program_that_cannot_run_on_the_changed_schema_fails_the_proof(self):
        work = self.root / 'breaking'
        work.mkdir()
        with self.assertRaises(Exception):
            P.proof(self.python, work, extra_migrations=self.steps(BREAK))
        self.assertEqual(__import__('json').loads((work / 'receipt.json').read_text())['result'], 'FAIL')

    def test_old_program_runs_on_a_migrated_copy_of_a_database(self):
        base = self.root / 'copy-base'
        base.mkdir()
        P.proof(self.python, base)
        source = base / 'fixture.db'
        migrated = self.root / 'migrated.db'
        mr.rehearse(source, self.steps(ADD), keep_copy=migrated)
        work = self.root / 'copy-work'
        work.mkdir()
        result = P.copy_proof(self.python, work, migrated)
        self.assertEqual(result['result'], 'COPY_ASSERTIONS_PASS')
        self.assertEqual(len(result['commands']), 2)

    def test_copy_proof_fails_on_a_copy_the_program_cannot_read(self):
        base = self.root / 'copy-base2'
        base.mkdir()
        P.proof(self.python, base)
        broken = self.root / 'broken.db'
        mr.rehearse(base / 'fixture.db', self.steps(BREAK), keep_copy=broken)
        work = self.root / 'copy-work2'
        work.mkdir()
        with self.assertRaises(Exception):
            P.copy_proof(self.python, work, broken)


if __name__ == '__main__':
    unittest.main()
