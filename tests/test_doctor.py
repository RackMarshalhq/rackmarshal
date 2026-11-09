from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rackmarshal import cli
from rackmarshal.core import doctor

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class DoctorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = self.root / "state.db"
        self.conf = self.root / "rackmarshal.conf"
        self.conf.write_text("STATE_DB=%s\nSITE_NAME=fictional\nENABLED_DOMAINS=\n" % self.db)
        self.resolv = self.root / "resolv.conf"
        self.resolv.write_text("nameserver 192.168.1.1\n")
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript(Path("rackmarshal/db/migrations/010_cycle_health.sql").read_text().replace(
                "INSERT INTO metadata", "-- INSERT INTO metadata").replace("VALUES ('cycle_health_schema', '1')", "").replace(
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value;", ""))
            c.commit()
        self.timers = {}

    def systemctl(self, verb, name):
        if self.timers.get(name) == "gone":
            return 1, "disabled"
        if verb == "is-active" and self.timers.get(name) == "inactive":
            return 3, "inactive"
        return 0, "enabled" if verb == "is-enabled" else "active"

    def run_doctor(self, **overrides):
        args = dict(systemctl=self.systemctl, getaddrinfo=lambda host, port: [("x",)],
                    fetch=lambda url: (200, {"status": "ok"}), resolv_conf=str(self.resolv), now=NOW)
        args.update(overrides)
        return doctor.run_doctor(str(self.conf), **args)

    def by_name(self, report):
        return {r["name"]: r for r in report["results"]}

    def test_healthy_install_has_no_failures(self):
        self.conf.write_text("STATE_DB=%s\nSITE_NAME=fictional\n" % self.db)
        report = self.run_doctor()
        self.assertEqual(report["failed"], 0, doctor.describe(report))
        self.assertIn("Everything checked looks good", doctor.describe(report).replace("\n", " "))

    def test_tailscale_only_dns_fails_with_the_container_fix(self):
        self.resolv.write_text("nameserver 100.100.100.100\n")
        item = self.by_name(self.run_doctor())["Name lookup (DNS)"]
        self.assertEqual(item["status"], "FAIL")
        self.assertIn("pct set", item["fix"])

    def test_unresolvable_configured_host_fails(self):
        self.conf.write_text("STATE_DB=%s\nSITE_NAME=fictional\nZFS_SSH_HOST=nowhere.invalid\n" % self.db)

        def refuse(host, port):
            raise OSError("no such host")
        item = self.by_name(self.run_doctor(getaddrinfo=refuse))["Name lookup (DNS)"]
        self.assertEqual(item["status"], "FAIL")

    def test_status_page_down_fails(self):
        def down(url):
            raise OSError("refused")
        item = self.by_name(self.run_doctor(fetch=down))["Status page"]
        self.assertEqual((item["status"], "rackmarshal-status.service" in item["fix"]), ("FAIL", True))

    def test_missing_database_fails(self):
        self.db.unlink()
        self.assertEqual(self.by_name(self.run_doctor())["Database"]["status"], "FAIL")

    def test_broken_settings_file_stops_early(self):
        self.conf.write_text("SITE_NAME=fictional\n")
        report = self.run_doctor()
        self.assertEqual([r["name"] for r in report["results"]], ["Settings file"])
        self.assertEqual(report["failed"], 1)

    def test_timer_checks_and_last_run_results(self):
        env, ca = self.root / "pve.env", self.root / "pve-ca.pem"
        for item in (env, ca):
            item.write_text("fixture\n")
            item.chmod(0o600)
        self.conf.write_text("STATE_DB=%s\nSITE_NAME=fictional\nENABLED_DOMAINS=pve\nPVE_API_ENV=%s\nPVE_CA_FILE=%s\n"
                             % (self.db, env, ca))
        self.timers["rackmarshal-domain@pve.timer"] = "inactive"
        names = self.by_name(self.run_doctor())
        self.assertEqual(names["Scheduled check: domain@pve"]["status"], "FAIL")
        self.assertEqual(names["Last run: pve"]["status"], "WARN")  # never ran
        unit = "rackmarshal-domain@pve.service"
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("INSERT INTO cycle_health(unit_name,health_state,last_result_at,last_failure_at)"
                      " VALUES(?,'FAILED','2026-01-01T11:55:00Z','2026-01-01T11:55:00Z')", (unit,))
            c.commit()
        self.assertEqual(self.by_name(self.run_doctor())["Last run: pve"]["status"], "FAIL")
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE cycle_health SET health_state='SUCCESS', last_success_at='2026-01-01T11:50:00Z'")
            c.commit()
        self.assertEqual(self.by_name(self.run_doctor())["Last run: pve"]["status"], "PASS")
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE cycle_health SET last_success_at='2026-01-01T08:00:00Z'")
            c.commit()
        self.assertEqual(self.by_name(self.run_doctor())["Last run: pve"]["status"], "WARN")

    def test_systemd_unavailable_is_a_warning_not_a_failure(self):
        self.conf.write_text("STATE_DB=%s\nSITE_NAME=fictional\n" % self.db)
        item = self.by_name(self.run_doctor(systemctl=lambda *a: (None, "")))["Scheduled checks"]
        self.assertEqual(item["status"], "WARN")

    def test_command_exit_codes(self):
        self.assertEqual(cli.COMMANDS["doctor"].__name__, "_cmd_doctor")
        self.assertEqual(cli._build_parser().parse_args(["doctor", "--config", str(self.conf)]).cmd, "doctor")


if __name__ == "__main__":
    unittest.main()
