"""A NEW backup incident recovers when the unlisted guest or job is no longer reported."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

MIGRATIONS = Path("rackmarshal/db/migrations")
GUEST = "fictional-guest"


class NewIncidentRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Path(directory.name) / "state.db"
        conf = Path(directory.name) / "rackmarshal.conf"
        conf.write_text(f"STATE_DB={self.db}\nSITE_NAME=fictional\n")
        self.env = dict(os.environ, RACKMARSHAL_CONFIG=str(conf), RACKMARSHAL_STATE_DB=str(self.db))
        done = subprocess.run(
            [sys.executable, str(MIGRATIONS / "migrate.py"), "--db", str(self.db),
             "--migrations-dir", str(MIGRATIONS), "--apply", "--yes"],
            capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.minute = 0

    def observe(self):
        self.minute += 1
        stamp = f"2026-01-01T03:{self.minute:02d}:00Z"
        with closing(sqlite3.connect(self.db)) as connection:
            observation = connection.execute(
                "INSERT INTO observations(collector, observed_at, source, schema_version, tls_verified,"
                " resource_count, payload_json) VALUES ('backup_domain',?,'t',1,1,0,'{}')",
                (stamp,)).lastrowid
            connection.commit()
        return observation, stamp

    def add_event(self, observation, stamp, kind, key):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute(
                "INSERT INTO backup_events(observation_id, resource_type, resource_key, outcome,"
                " changes_json, observed_at) VALUES (?,?,?,'NEW','[]',?)", (observation, kind, key, stamp))
            connection.commit()

    def process(self, extra=()):
        """Process one observation holding the always-present guest plus any extra NEW resources."""
        observation, stamp = self.observe()
        results = [{"resource_type": "backup_guest", "resource_key": GUEST, "display_name": "Fictional Guest",
                    "outcome": "MATCH", "baseline_state": "VERIFIED", "changes": []}]
        for kind, key in extra:
            self.add_event(observation, stamp, kind, key)
            results.append({"resource_type": kind, "resource_key": key, "display_name": key,
                            "outcome": "NEW", "baseline_state": None, "changes": []})
        payload = {"schema_version": 1, "comparator": "backup_baseline",
                   "observation_id": observation, "observed_at": stamp, "results": results}
        done = subprocess.run(
            [sys.executable, "-m", "rackmarshal.domains.backup.incidents", "--database", str(self.db)],
            input=json.dumps(payload), text=True, capture_output=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def states(self):
        with closing(sqlite3.connect(self.db)) as connection:
            return {(kind, key): state for kind, key, state in connection.execute(
                "SELECT resource_type, resource_key, incident_state FROM backup_incidents")}

    def test_new_guest_incident_recovers_when_the_guest_disappears(self):
        self.process()
        opened = self.process([("backup_guest", "777")])
        self.assertEqual(opened["incidents_opened"], 1)
        self.assertEqual(self.states(), {("backup_guest", "777"): "OPEN"})
        recovered = self.process()
        self.assertEqual(recovered["incidents_recovered"], 1)
        self.assertEqual(self.states(), {("backup_guest", "777"): "RECOVERED"})

    def test_new_job_incident_recovers_when_the_job_disappears(self):
        self.process()
        self.process([("backup_job", "stray-job")])
        self.process()
        self.assertEqual(self.states(), {("backup_job", "stray-job"): "RECOVERED"})

    def test_new_incident_stays_open_while_the_guest_is_still_reported(self):
        self.process()
        self.process([("backup_guest", "777")])
        again = self.process([("backup_guest", "777")])
        self.assertEqual(again["incidents_ongoing"], 1)
        self.assertEqual(again["incidents_recovered"], 0)
        self.assertEqual(self.states(), {("backup_guest", "777"): "OPEN"})

    def test_missing_incident_is_not_recovered_by_absence(self):
        self.process()
        with closing(sqlite3.connect(self.db)) as connection:
            observation = connection.execute("SELECT MAX(id) FROM observations").fetchone()[0]
            event = connection.execute(
                "INSERT INTO backup_events(observation_id, resource_type, resource_key, outcome,"
                " changes_json, observed_at) VALUES (?,'backup_guest','888','MISSING','[]','2026-01-01T03:01:00Z')",
                (observation,)).lastrowid
            connection.execute(
                "INSERT INTO backup_incidents(resource_type, resource_key, display_name, incident_type,"
                " incident_state, opened_event_id, last_event_id, opened_observation_id,"
                " last_abnormal_observation_id, opened_at, last_abnormal_at, opening_changes_json,"
                " latest_changes_json) VALUES ('backup_guest','888','x','MISSING','OPEN',?,?,?,?,"
                "'2026-01-01T03:01:00Z','2026-01-01T03:01:00Z','[]','[]')",
                (event, event, observation, observation))
            connection.commit()
        self.process()
        self.assertEqual(self.states(), {("backup_guest", "888"): "OPEN"})


if __name__ == "__main__":
    unittest.main()
