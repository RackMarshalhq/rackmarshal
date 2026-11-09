from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rackmarshal import cli
from rackmarshal.maintenance import retire_guest as rg

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class RetireGuestTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = self.root / "state.db"
        self.observed = "2026-01-01T11:59:00Z"
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript(Path("rackmarshal/db/migrations/001_pve_ledger.sql").read_text())
            self.observe(c, [{"type": "lxc", "vmid": 9002, "name": "Alive", "status": "running"}])
            for kind, key, name in (("lxc", "9001", "Gone A"), ("lxc", "9002", "Alive"), ("qemu", "9003", "Gone B")):
                c.execute("INSERT INTO resource_baseline(resource_type,resource_key,display_name,expected_status,"
                          "baseline_state) VALUES(?,?,?,'running','VERIFIED')", (kind, key, name))
            c.commit()

    def observe(self, c, resources, observed=None, tls=1):
        c.execute("INSERT INTO observations(collector,observed_at,source,schema_version,tls_verified,"
                  "resource_count,payload_json) VALUES('pve_cluster_resources',?,'t',1,?,?,?)",
                  (observed or self.observed, tls, len(resources), json.dumps({"resources": resources})))

    def keys(self):
        with closing(sqlite3.connect(self.db)) as c:
            return sorted(r[0] for r in c.execute("SELECT resource_key FROM resource_baseline"))

    def run_retire(self, guests, **kw):
        return rg.retire(self.db, guests, now=NOW, backup_dir=self.root / "bk", **kw)

    def test_plan_names_guest_without_an_observation_number_and_writes_nothing(self):
        result = self.run_retire(["9001", "9003"])
        self.assertEqual(result["state"], "PLANNED")
        self.assertEqual([e["action"] for e in result["guests"]], ["RETIRE", "RETIRE"])
        self.assertEqual(self.keys(), ["9001", "9002", "9003"])
        self.assertIn("Nothing has been changed", rg.describe(result))

    def test_apply_removes_only_named_rows_and_saves_a_copy(self):
        result = self.run_retire(["lxc:9001"], note="deleted test container", apply=True)
        self.assertEqual(result["state"], "APPLIED")
        self.assertEqual(self.keys(), ["9002", "9003"])
        with closing(sqlite3.connect(result["backup"])) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM resource_baseline").fetchone()[0], 3)
        self.assertTrue((Path(result["backup"]).parent / "receipt.json").exists())

    def test_live_guest_is_refused_and_nothing_changes(self):
        result = self.run_retire(["9001", "9002"], note="x", apply=True)
        self.assertEqual(result["state"], "REFUSED")
        self.assertEqual(self.keys(), ["9001", "9002", "9003"])
        self.assertIn("still lists", rg.describe(result))

    def test_unknown_guest_is_skipped(self):
        result = self.run_retire(["4242"], note="x", apply=True)
        self.assertEqual(result["state"], "NOTHING_TO_DO")
        self.assertEqual(self.keys(), ["9001", "9002", "9003"])

    def test_apply_needs_a_note(self):
        with self.assertRaisesRegex(rg.RetireError, "--note"):
            self.run_retire(["9001"], apply=True)

    def test_stale_or_unverified_observation_is_refused(self):
        with closing(sqlite3.connect(self.db)) as c:
            self.observe(c, [], observed="2026-01-01T11:00:00Z")
            c.commit()
        with self.assertRaisesRegex(rg.RetireError, "minutes old"):
            self.run_retire(["9001"])
        with closing(sqlite3.connect(self.db)) as c:
            self.observe(c, [], tls=0)
            c.commit()
        with self.assertRaisesRegex(rg.RetireError, "certificate"):
            self.run_retire(["9001"])

    def test_no_observation_and_bad_numbers_are_explained(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("DELETE FROM observations")
            c.commit()
        with self.assertRaisesRegex(rg.RetireError, "no Proxmox observation"):
            self.run_retire(["9001"])
        with self.assertRaisesRegex(rg.RetireError, "not a guest number"):
            rg._parse_ids(["abc"])

    def test_cli_command_is_registered_and_plans(self):
        conf = self.root / "rackmarshal.conf"
        conf.write_text("STATE_DB=%s\nSITE_NAME=fictional\n" % self.db)
        args = cli._build_parser().parse_args(["retire-guest", "9001", "--config", str(conf)])
        self.assertEqual(args.guests, ["9001"])
        self.assertFalse(args.apply)
        self.assertEqual(cli.COMMANDS["retire-guest"].__name__, "_cmd_retire_guest")


if __name__ == "__main__":
    unittest.main()
