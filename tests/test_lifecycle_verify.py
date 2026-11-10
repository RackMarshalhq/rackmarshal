"""Health proof after an upgrade: one successful run of each enabled check, then a clean doctor."""
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lifecycle_verify", ROOT / "scripts/lifecycle.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)

SINCE = "2026-01-01T12:00:00.000000Z"
BEFORE = "2026-01-01T11:00:00.000000Z"
AFTER = "2026-01-01T12:05:00.000000Z"


class FakeClock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class VerifyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Path(directory.name) / "state.db"
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript(Path("rackmarshal/db/migrations/010_cycle_health.sql").read_text().replace(
                "INSERT INTO metadata", "-- INSERT INTO metadata").replace("VALUES ('cycle_health_schema', '1')", "").replace(
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value;", ""))
            c.commit()
        self.clock = FakeClock()

    def record(self, domain, state, success=None, failure=None):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("INSERT OR REPLACE INTO cycle_health(unit_name,health_state,last_result_at,last_success_at,last_failure_at)"
                      " VALUES(?,?,?,?,?)", ("rackmarshal-domain@%s.service" % domain, state, success or failure, success, failure))
            c.commit()

    def wait(self, domains, timeout=60):
        C.wait_for_domain_runs(self.db, domains, SINCE, timeout, self.clock.sleep, self.clock, interval=10)

    def test_returns_when_every_domain_succeeded_after_the_floor(self):
        self.record("pve", "SUCCESS", success=AFTER)
        self.record("zfs", "SUCCESS", success=AFTER)
        self.wait(["pve", "zfs"])
        self.assertEqual(self.clock.now, 0)

    def test_waits_for_a_domain_that_has_not_run_yet(self):
        self.record("pve", "SUCCESS", success=AFTER)
        original = self.clock.sleep

        def sleeper(seconds):
            original(seconds)
            self.record("zfs", "SUCCESS", success=AFTER)
        C.wait_for_domain_runs(self.db, ["pve", "zfs"], SINCE, 60, sleeper, self.clock, interval=10)
        self.assertEqual(self.clock.now, 10)

    def test_a_success_from_before_the_upgrade_does_not_count(self):
        self.record("pve", "SUCCESS", success=BEFORE)
        with self.assertRaisesRegex(C.VerifyFailed, "no successful run yet for: pve"):
            self.wait(["pve"])

    def test_a_failure_after_the_floor_fails_immediately(self):
        self.record("pve", "FAILED", success=BEFORE, failure=AFTER)
        with self.assertRaisesRegex(C.VerifyFailed, "domain pve failed after the upgrade"):
            self.wait(["pve"])
        self.assertEqual(self.clock.now, 0)

    def test_an_old_failure_followed_by_a_new_success_is_fine(self):
        self.record("pve", "SUCCESS", success=AFTER, failure=BEFORE)
        self.wait(["pve"])

    def test_timeout_names_every_domain_still_waiting(self):
        self.record("pve", "SUCCESS", success=AFTER)
        with self.assertRaisesRegex(C.VerifyFailed, "zfs, hardware"):
            self.wait(["pve", "zfs", "hardware"], timeout=30)

    def test_doctor_failure_fails_the_proof_and_success_returns_its_text(self):
        self.record("pve", "SUCCESS", success=AFTER)
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=2, stdout="[FAIL] Status page: down\n", stderr="")
        with self.assertRaisesRegex(C.VerifyFailed, "Status page: down"):
            C.health_after_resume("/py", "/conf", self.db, ["pve"], SINCE, 30, runner, self.clock.sleep, self.clock)
        self.assertEqual(calls[0], ["/py", "-I", "-B", "-m", "rackmarshal.cli", "doctor", "--config", "/conf"])
        ok = C.health_after_resume("/py", "/conf", self.db, ["pve"], SINCE, 30,
                                   lambda *a, **k: SimpleNamespace(returncode=0, stdout="all good\n", stderr=""),
                                   self.clock.sleep, self.clock)
        self.assertEqual(ok, "all good\n")


if __name__ == "__main__":
    unittest.main()
