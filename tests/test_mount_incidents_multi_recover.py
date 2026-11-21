"""Regression: one mount with two OPEN incident types recovering in one observation.

A mount can accumulate more than one OPEN incident (e.g. MOUNT_MISSING, then
MOUNT_WRONG_SOURCE on a later observation). When the mount later comes back
``ok``, both incidents recover in the same observation. mount_events has
UNIQUE(observation_id, mount_id, outcome), so the processor must write a single
RECOVERED event for the mount and attach it to every incident it recovers.
"""

import importlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

MOUNT = {
    "id": "fictional-mount",
    "guest_kind": "host",
    "guest_id": "",
    "mountpoint": "/mnt/fictional",
    "optional": False,
    "expected_source": "fictional:/share",
    "fstype": "nfs",
    "severity_missing": "warning",
}


class MountMultiRecoverTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        root = Path(self.td.name)
        self.db = root / "state.db"
        conf = root / "rackmarshal.conf"
        conf.write_text(f"STATE_DB={self.db}\nSITE_NAME=fictional\n")
        self._old_env = {k: os.environ.get(k) for k in ("RACKMARSHAL_CONFIG", "RACKMARSHAL_STATE_DB")}
        os.environ["RACKMARSHAL_CONFIG"] = str(conf)
        os.environ["RACKMARSHAL_STATE_DB"] = str(self.db)
        import rackmarshal.core.config as cfg

        self._old_conf = cfg.DEFAULT_CONFIG_FILE
        cfg.DEFAULT_CONFIG_FILE = conf
        from rackmarshal.db.migrations import migrate

        old = sys.argv
        sys.argv = ["migrate", "--db", str(self.db), "--apply", "--yes"]
        try:
            migrate.main()
        finally:
            sys.argv = old
        sys.modules.pop("rackmarshal.domains.mount.incidents", None)
        self.m = importlib.import_module("rackmarshal.domains.mount.incidents")
        self.con = sqlite3.connect(self.db)
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        self.con.close()
        import rackmarshal.core.config as cfg

        cfg.DEFAULT_CONFIG_FILE = self._old_conf
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("rackmarshal.domains.mount.incidents", None)
        self.td.cleanup()

    def _observe(self, at, state, observed_source=None):
        row = dict(MOUNT, state=state, observed_source=observed_source)
        problem = 0 if state == "ok" else 1
        self.con.execute(
            "insert into mount_observations(observed_at,source,schema_version,"
            "checked_count,ok_count,problem_count,payload_json) values(?,?,?,?,?,?,?)",
            (at, "fictional", 1, 1, 1 - problem, problem, json.dumps({"results": [row]})),
        )
        self.con.commit()
        return self.m.process(self.con)

    def test_two_open_types_recover_in_same_observation(self):
        r = self._observe("2026-01-01T00:00:00Z", "missing")
        self.assertEqual(r["opened"], 1)
        r = self._observe("2026-01-01T00:05:00Z", "wrong_source", "fictional:/other")
        self.assertEqual(r["opened"], 1)
        self.assertEqual(r["open_problems"], 2)

        r = self._observe("2026-01-01T00:10:00Z", "ok", "fictional:/share")
        self.assertEqual(r["recovered"], 2)
        self.assertEqual(r["open_problems"], 0)

        oid = r["observation_id"]
        events = self.con.execute(
            "select id from mount_events where observation_id=? and mount_id=? and outcome='RECOVERED'",
            (oid, MOUNT["id"]),
        ).fetchall()
        self.assertEqual(len(events), 1)
        eid = events[0]["id"]
        rows = self.con.execute(
            "select incident_type, incident_state, last_event_id, recovered_observation_id "
            "from mount_incidents order by id"
        ).fetchall()
        self.assertEqual([x["incident_type"] for x in rows], ["MOUNT_MISSING", "MOUNT_WRONG_SOURCE"])
        for x in rows:
            self.assertEqual(x["incident_state"], "RECOVERED")
            self.assertEqual(x["last_event_id"], eid)
            self.assertEqual(x["recovered_observation_id"], oid)
        cursors = self.con.execute(
            "select last_processed_event_id from mount_incident_processing"
        ).fetchall()
        self.assertEqual({c[0] for c in cursors}, {eid})

    def test_single_recovery_unchanged(self):
        self._observe("2026-01-01T00:00:00Z", "missing")
        r = self._observe("2026-01-01T00:05:00Z", "ok", "fictional:/share")
        self.assertEqual(r["recovered"], 1)
        self.assertEqual(r["open_problems"], 0)


if __name__ == "__main__":
    unittest.main()
