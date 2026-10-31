import contextlib
import io
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from rackmarshal.db.migrations import migrate
from rackmarshal.maintenance import prune

NOW = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
OLD, NEW = "2026-08-01T00:00:00", "2026-10-30T00:00:00"  # 91 and 1 days old


def make_db(path):
    with contextlib.closing(sqlite3.connect(path)) as c:
        for sql in migrate.discover_sql(migrate.MIG_DIR):
            c.executescript(sql.read_text())
        c.commit()


def insert(c, table, observed_at, collector="pve"):
    if table == "observations":
        cur = c.execute("INSERT INTO observations (collector, observed_at, source, schema_version, tls_verified, resource_count, payload_json) VALUES (?,?,?,?,?,?,?)", (collector, observed_at, "t", 1, 1, 0, "{}"))
    elif table == "zfs_observations":
        cur = c.execute("INSERT INTO zfs_observations (observed_at, source, schema_version, host_key_verified, pool_count, payload_json) VALUES (?,?,?,?,?,?)", (observed_at, "t", 1, 1, 0, "{}"))
    elif table == "mount_observations":
        cur = c.execute("INSERT INTO mount_observations (observed_at, source, schema_version, checked_count, ok_count, problem_count, payload_json) VALUES (?,?,?,?,?,?,?)", (observed_at, "t", 1, 0, 0, 0, "{}"))
    else:
        cur = c.execute("INSERT INTO hardware_observations (observed_at, host, serial, role, present, status) VALUES (?,?,?,?,?,?)", (observed_at, "h", observed_at, "r", 1, "OK"))
    return cur.lastrowid


def count(path, table):
    with contextlib.closing(sqlite3.connect(path)) as c:
        return c.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.db = str(Path(self.dir.name) / "state.db")
        make_db(self.db)

    def seed(self):
        with contextlib.closing(sqlite3.connect(self.db)) as c:
            for table in prune.TABLES:
                for stamp in (OLD, "2026-08-02T00:00:00", "2026-08-03T00:00:00", NEW):
                    insert(c, table, stamp)
            c.commit()

    def test_deletes_old_keeps_new_and_newest(self):
        self.seed()
        result = prune.prune(self.db, 35, now=NOW)
        for table in prune.TABLES:
            self.assertEqual(result[table], 2, table)
            self.assertEqual(count(self.db, table), 2, table)

    def test_dry_run_changes_nothing(self):
        self.seed()
        result = prune.prune(self.db, 35, dry_run=True, now=NOW)
        self.assertEqual(result["zfs_observations"], 2)
        self.assertEqual(count(self.db, "zfs_observations"), 4)

    def test_keeps_newest_two_even_when_everything_is_old(self):
        with contextlib.closing(sqlite3.connect(self.db)) as c:
            for stamp in (OLD, "2026-08-02T00:00:00", "2026-08-03T00:00:00", "2026-08-04T00:00:00"):
                insert(c, "zfs_observations", stamp)
            c.commit()
        prune.prune(self.db, 35, now=NOW)
        self.assertEqual(count(self.db, "zfs_observations"), 2)

    def test_observations_keep_newest_per_collector(self):
        with contextlib.closing(sqlite3.connect(self.db)) as c:
            for collector in ("pve", "ha"):
                for stamp in (OLD, "2026-08-02T00:00:00", "2026-08-03T00:00:00"):
                    insert(c, "observations", stamp, collector)
            c.commit()
        prune.prune(self.db, 35, now=NOW)
        self.assertEqual(count(self.db, "observations"), 4)

    def test_referenced_old_observation_is_kept(self):
        with contextlib.closing(sqlite3.connect(self.db)) as c:
            keep = insert(c, "mount_observations", OLD)
            for stamp in ("2026-08-02T00:00:00", "2026-08-03T00:00:00", "2026-08-04T00:00:00"):
                insert(c, "mount_observations", stamp)
            c.execute("INSERT INTO mount_events (observation_id, mount_id, guest_kind, guest_id, mountpoint, outcome, changes_json, observed_at) VALUES (?,?,?,?,?,?,?,?)", (keep, "m", "lxc", "1", "/x", "MISSING", "{}", OLD))
            c.commit()
        result = prune.prune(self.db, 35, now=NOW)
        self.assertEqual(result["mount_observations"], 1)
        with contextlib.closing(sqlite3.connect(self.db)) as c:
            self.assertIsNotNone(c.execute("SELECT 1 FROM mount_observations WHERE id=?", (keep,)).fetchone())

    def test_batches(self):
        with contextlib.closing(sqlite3.connect(self.db)) as c:
            for i in range(25):
                insert(c, "zfs_observations", "2026-08-%02dT00:00:00" % (i + 1) if i < 28 else OLD)
            c.commit()
        result = prune.prune(self.db, 35, now=NOW, batch=10)
        self.assertEqual(result["zfs_observations"], 23)
        self.assertEqual(count(self.db, "zfs_observations"), 2)

    def add_processing(self, c, table, ids):
        if table == "zfs_incident_processing":
            for i in ids:
                c.execute("INSERT INTO zfs_incident_processing (observation_id, differences_detected, incidents_opened, incidents_ongoing, incidents_recovered, note) VALUES (?,?,?,?,?,?)", (i, 0, 0, 0, 0, "t"))
        else:
            for i in ids:
                c.execute("INSERT INTO %s (observation_id, processing_kind) VALUES (?, 'PROCESSED')" % table, (i,))

    def test_processing_rows_are_retired_with_their_observation_but_checkpoint_stays(self):
        pairs = [("incident_processing", "observations"), ("ha_incident_processing", "observations"),
                 ("backup_incident_processing", "observations"), ("zfs_incident_processing", "zfs_observations")]
        for proc, obs in pairs:
            with self.subTest(proc):
                db = str(Path(self.dir.name) / (proc + ".db")); make_db(db)
                with contextlib.closing(sqlite3.connect(db)) as c:
                    ids = [insert(c, obs, "2026-08-%02dT00:00:00" % (d + 1)) for d in range(6)] + [insert(c, obs, NEW)]
                    self.add_processing(c, proc, ids)
                    c.commit()
                result = prune.prune(db, 35, now=NOW)
                # the newest two (ids 6 old, 7 new) stay; the other five go with their processing rows
                self.assertEqual(result[obs], 5); self.assertEqual(result[proc], 5)
                with contextlib.closing(sqlite3.connect(db)) as c:
                    self.assertEqual([r[0] for r in c.execute("SELECT observation_id FROM %s ORDER BY 1" % proc)], ids[5:])

    def test_checkpoint_is_kept_even_if_it_is_old_and_not_newest(self):
        db = self.db
        with contextlib.closing(sqlite3.connect(db)) as c:
            ids = [insert(c, "observations", "2026-08-%02dT00:00:00" % (d + 1), "pve") for d in range(5)]
            self.add_processing(c, "incident_processing", ids[:3])  # processor stopped at the third observation
            c.commit()
        prune.prune(db, 35, now=NOW)
        with contextlib.closing(sqlite3.connect(db)) as c:
            self.assertEqual([r[0] for r in c.execute("SELECT observation_id FROM incident_processing")], [ids[2]])
            self.assertEqual([r[0] for r in c.execute("SELECT id FROM observations ORDER BY id")], ids[2:])

    def test_dry_run_reports_processing_rows(self):
        with contextlib.closing(sqlite3.connect(self.db)) as c:
            ids = [insert(c, "observations", "2026-08-%02dT00:00:00" % (d + 1), "pve") for d in range(5)]
            self.add_processing(c, "incident_processing", ids)
            c.commit()
        result = prune.prune(self.db, 35, dry_run=True, now=NOW)
        self.assertEqual((result["observations"], result["incident_processing"]), (3, 3))
        self.assertEqual(count(self.db, "incident_processing"), 5)

    def test_refuses_short_retention(self):
        with self.assertRaises(ValueError):
            prune.prune(self.db, 3, now=NOW)

    def test_cli(self):
        self.seed()
        os.environ["RACKMARSHAL_STATE_DB"] = self.db
        self.addCleanup(os.environ.pop, "RACKMARSHAL_STATE_DB", None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(prune.main(["--dry-run", "--days", "35"]), 0)
        self.assertIn("would delete 2 rows", out.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(prune.main(["--days", "2"]), 1)
        self.assertIn("PRUNE FAILED", err.getvalue())

    def test_missing_database_fails_cleanly(self):
        os.environ["RACKMARSHAL_STATE_DB"] = str(Path(self.dir.name) / "nope" / "state.db")
        self.addCleanup(os.environ.pop, "RACKMARSHAL_STATE_DB", None)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(prune.main([]), 1)

if __name__ == "__main__":
    unittest.main()
