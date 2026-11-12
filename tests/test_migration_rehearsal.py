from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rackmarshal.db.migrations import migrate
from rackmarshal.maintenance import migration_rehearsal as mr


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Path(directory.name) / "state.db"
        with closing(sqlite3.connect(self.db)) as c:
            migrate.ensure_ledger(c)
            c.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT)")
            c.executemany("INSERT INTO items(name) VALUES(?)", [("a",), ("b",)])
            c.commit()

    def rehearse(self, *sqls):
        return mr.rehearse(self.db, [("%03d_x" % (i + 10), s, sha(s)) for i, s in enumerate(sqls)])

    def real_digest(self):
        return hashlib.sha256(self.db.read_bytes()).hexdigest()

    def test_adding_a_table_is_clean_and_real_db_untouched(self):
        before = self.real_digest()
        result = self.rehearse("CREATE TABLE extra(x);")
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["added_tables"], ["extra"])
        self.assertEqual(self.real_digest(), before)

    def test_adding_a_column_is_clean(self):
        self.assertEqual(self.rehearse("ALTER TABLE items ADD COLUMN note TEXT;")["problems"], [])

    def test_rebuilding_a_table_with_rows_kept_is_clean(self):
        sql = ("ALTER TABLE items RENAME TO items_old;\n"
               "CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT, extra TEXT);\n"
               "INSERT INTO items(id,name) SELECT id,name FROM items_old;\n"
               "DROP TABLE items_old;\n")
        self.assertEqual(self.rehearse(sql)["problems"], [])

    def test_metadata_markers_may_change_but_not_vanish(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            c.execute("INSERT INTO metadata VALUES('old_marker','1')")
        bump = "INSERT INTO metadata(key,value) VALUES('old_marker','2') ON CONFLICT(key) DO UPDATE SET value=excluded.value;" \
               "INSERT INTO metadata VALUES('new_marker','1');"
        self.assertEqual(self.rehearse(bump)["problems"], [])
        self.assertEqual(self.rehearse("DELETE FROM metadata;")["problems"], ["metadata keys old_marker would disappear"])

    def test_dropping_table_columns_or_rows_is_reported(self):
        self.assertIn("table items would disappear", self.rehearse("DROP TABLE items;")["problems"])
        self.assertTrue(any("lose column" in p for p in self.rehearse(
            "ALTER TABLE items DROP COLUMN name;")["problems"]))
        self.assertIn("rows in table items would change", self.rehearse("DELETE FROM items WHERE id=1;")["problems"])

    def test_failing_sql_is_a_plain_refusal(self):
        with self.assertRaises(mr.RehearsalError):
            self.rehearse("CREATE TABLE bad(;")

    def test_apply_all_is_all_or_nothing(self):
        with closing(sqlite3.connect(self.db, isolation_level=None)) as c:
            with self.assertRaises(sqlite3.Error):
                mr.apply_all(c, [("010_a", "CREATE TABLE one(x);", sha("a")),
                                 ("011_b", "CREATE TABLE items(x);", sha("b"))])
            names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE name='one'")]
            self.assertEqual(names, [])
            self.assertEqual(c.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 0)

    def test_apply_all_keeps_nothing_when_result_differs_from_expectation(self):
        with closing(sqlite3.connect(self.db, isolation_level=None)) as c:
            before = mr.schema_fingerprint(c)
            with self.assertRaises(mr.RehearsalError):
                mr.apply_all(c, [("010_a", "CREATE TABLE one(x);", sha("a"))], expect=("0" * 64, []))
            self.assertEqual(mr.schema_fingerprint(c), before)

    def test_keep_copy_saves_the_migrated_copy(self):
        keep = self.db.with_name("kept.db")
        self.rehearse_keep(keep)
        with closing(sqlite3.connect(keep)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM extra").fetchone()[0], 0)
        self.assertEqual(oct(keep.stat().st_mode & 0o777), "0o600")

    def rehearse_keep(self, keep):
        s = "CREATE TABLE extra(x);"
        return mr.rehearse(self.db, [("010_x", s, sha(s))], keep_copy=keep)

    def test_truncated_statement_is_refused(self):
        with self.assertRaises(mr.RehearsalError):
            list(mr.statements("CREATE TABLE t(x);\nSELECT 1 +"))

    def test_several_statements_on_one_line_and_semicolons_in_text(self):
        sql = "CREATE TABLE t(x); INSERT INTO t VALUES('a;b'); -- note; here\nINSERT INTO t VALUES(2);\n"
        self.assertEqual(len(list(mr.statements(sql))), 3)

    def test_triggers_stay_whole_and_order_key(self):
        sql = "CREATE TABLE t(x);\nCREATE TRIGGER g AFTER INSERT ON t BEGIN SELECT 1; SELECT 2; END;\n"
        self.assertEqual(len(list(mr.statements(sql))), 2)
        self.assertLess(mr.migration_order_key("010_a"), mr.migration_order_key("010b_a"))
        with self.assertRaises(mr.RehearsalError):
            mr.migration_order_key("abc")

    def test_all_repo_migrations_match_the_normal_runner(self):
        folder = Path(migrate.__file__).parent
        files = sorted(folder.glob("[0-9][0-9][0-9]*.sql"), key=lambda f: mr.migration_order_key(f.stem))
        triples = [(f.stem, f.read_text(), sha(f.read_text())) for f in files]
        fingerprints = []
        for use_apply_all in (True, False):
            path = self.db.with_name("fresh%s.db" % use_apply_all)
            with closing(sqlite3.connect(path, isolation_level=None)) as c:
                migrate.ensure_ledger(c)
                if use_apply_all:
                    mr.apply_all(c, triples)
                else:
                    for _, sql, _ in triples:
                        c.executescript(sql)
                fingerprints.append(sorted(c.execute("SELECT type,name,sql FROM sqlite_master WHERE name!='schema_migrations'")))
        self.assertEqual(fingerprints[0], fingerprints[1])


if __name__ == "__main__":
    unittest.main()
