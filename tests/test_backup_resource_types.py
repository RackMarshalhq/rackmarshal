"""Qualify migration 011: the backup ledger accepts all eight resource types."""
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

MIGRATIONS = Path("rackmarshal/db/migrations")
TYPES = (
    "backup_job", "backup_guest", "backup_scheduled_run", "backup_timemachine",
    "backup_phone", "backup_messages", "backup_host_verify", "backup_rsync_filebackups",
)


def apply(db, directory):
    result = subprocess.run(
        [sys.executable, str(MIGRATIONS / "migrate.py"), "--db", str(db),
         "--migrations-dir", str(directory), "--apply", "--yes"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def add_observation(connection):
    return connection.execute(
        "INSERT INTO observations(collector, observed_at, source, schema_version, tls_verified,"
        " resource_count, payload_json) VALUES ('backup','2026-01-01T00:00:00Z','t',1,1,0,'{}')"
    ).lastrowid


def add_event(connection, observation, kind, key="k"):
    return connection.execute(
        "INSERT INTO backup_events(observation_id, resource_type, resource_key, outcome,"
        " changes_json, observed_at) VALUES (?,?,?,'MISSING','{}','2026-01-01T00:00:00Z')",
        (observation, kind, key)).lastrowid


def add_incident(connection, observation, event, kind, key="k"):
    return connection.execute(
        "INSERT INTO backup_incidents(resource_type, resource_key, display_name, incident_type,"
        " incident_state, opened_event_id, last_event_id, opened_observation_id,"
        " last_abnormal_observation_id, opened_at, last_abnormal_at, opening_changes_json,"
        " latest_changes_json) VALUES (?,?,?,'MISSING','OPEN',?,?,?,?,"
        "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','{}','{}')",
        (kind, key, key, event, event, observation, observation)).lastrowid


class BackupResourceTypeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_fresh_install_accepts_every_resource_type(self):
        db = self.root / "fresh.db"
        apply(db, MIGRATIONS)
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            observation = add_observation(connection)
            for kind in TYPES:
                add_incident(connection, observation, add_event(connection, observation, kind), kind)
            connection.commit()
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM backup_incidents").fetchone()[0], 8)
            with self.assertRaises(sqlite3.IntegrityError):
                add_event(connection, observation, "backup_unknown")
            with self.assertRaises(sqlite3.IntegrityError):
                add_incident(connection, observation, 1, "backup_job")
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_backup_events_%' OR name LIKE 'idx_backup_incidents_%'")}
            self.assertEqual(indexes, {
                "idx_backup_events_observation", "idx_backup_events_resource",
                "idx_backup_incidents_one_open", "idx_backup_incidents_state",
                "idx_backup_incidents_resource"})

    def test_upgrade_preserves_rows_ids_and_sequence(self):
        old = self.root / "old"
        old.mkdir()
        for path in MIGRATIONS.glob("*.sql"):
            if not path.name.startswith("011_"):
                shutil.copy(path, old / path.name)
        db = self.root / "upgrade.db"
        apply(db, old)
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            observation = add_observation(connection)
            first = add_event(connection, observation, "backup_job", "a")
            doomed = add_event(connection, observation, "backup_guest", "b")
            incident = add_incident(connection, observation, first, "backup_job", "a")
            connection.execute("DELETE FROM backup_events WHERE id=?", (doomed,))
            connection.commit()
        apply(db, MIGRATIONS)
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            self.assertEqual(connection.execute("SELECT id, resource_key FROM backup_events").fetchall(), [(first, "a")])
            self.assertEqual(connection.execute("SELECT id, opened_event_id FROM backup_incidents").fetchall(), [(incident, first)])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertGreater(add_event(connection, observation, "backup_phone"), doomed)
            self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key='backup_ledger_schema'").fetchone()[0], "2")


if __name__ == "__main__":
    unittest.main()
