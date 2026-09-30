"""Qualify final systemd outcomes against an isolated durable ledger."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from rackmarshal.selfwatch.cycle_health import record, systemd_result


class CycleHealthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "fixture.db"
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
            connection.executescript(Path("rackmarshal/db/migrations/010_cycle_health.sql").read_text())

    def test_failure_recovery_preserves_history_and_exact_unit_identity(self):
        name = "rackmarshal-domain@backup.service"
        first = record(self.db, name, "SUCCESS", 1, 0, {})
        failed = record(self.db, name, "FAILED", 1, 7, {})
        again = record(self.db, name, "FAILED", 2, None, {})
        recovered = record(self.db, name, "SUCCESS", 1, 0, {})
        self.assertEqual(failed["last_success_at"], first["last_result_at"])
        self.assertEqual(recovered["last_failure_at"], again["last_result_at"])
        self.assertEqual(recovered["failure_count"], 2)
        self.assertEqual(recovered["last_success_at"], recovered["last_result_at"])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT unit_name FROM cycle_health").fetchall(), [(name,)])
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("metadata",), ("cycle_health",)])

    def test_final_success_and_invocation_provenance(self):
        result = systemd_result(dict(SERVICE_RESULT="success", EXIT_CODE="exited", EXIT_STATUS="0", INVOCATION_ID="fixture"))
        self.assertEqual(result[:3], ("SUCCESS", 1, 0))
        self.assertEqual(result[3]["invocation_id"], "fixture")

    def test_noncompletion_cannot_claim_success(self):
        for result, code, status in [("exit-code", "exited", "7"), ("signal", "killed", "TERM"),
                                      ("core-dump", "dumped", "ABRT"), ("timeout", "", ""),
                                      ("success", "killed", "TERM"), ("success", "", ""),
                                      ("future-result", "", "")]:
            with self.subTest(result=result, code=code):
                self.assertEqual(systemd_result(dict(SERVICE_RESULT=result, EXIT_CODE=code, EXIT_STATUS=status))[0], "FAILED")
        self.assertEqual(systemd_result(dict(SERVICE_RESULT="signal", EXIT_CODE="killed", EXIT_STATUS="TERM"))[1:3], (2, None))

    def invoke(self, *args, **environment):
        env = dict(os.environ)
        for key in ("SERVICE_RESULT", "EXIT_CODE", "EXIT_STATUS", "INVOCATION_ID"):
            env.pop(key, None)
        env.update(environment)
        return subprocess.run([sys.executable, "-W", "error::ResourceWarning", "-m", "rackmarshal.selfwatch.cycle_health",
                               "--unit", "rackmarshal-self-watch.service", "--db", str(self.db), *args],
                              env=env, capture_output=True, text=True, timeout=10)

    def test_cli_records_actual_environment(self):
        process = self.invoke("--from-systemd", SERVICE_RESULT="exit-code", EXIT_CODE="exited", EXIT_STATUS="7")
        self.assertEqual(process.returncode, 0, process.stderr)
        row = json.loads(process.stdout)["row"]
        self.assertEqual((row["health_state"], row["last_exit_status"], row["failure_count"]), ("FAILED", 7, 1))
        self.assertEqual(json.loads(row["detail_json"])["source"], "systemd.ExecStopPost")

    def test_missing_environment_and_metadata_overrides_do_not_write(self):
        for arguments in [("--from-systemd",), ("--from-systemd", "--detail", '{"fake":true}'),
                          ("--from-systemd", "--state", "SUCCESS")]:
            process = self.invoke(*arguments)
            self.assertNotEqual(process.returncode, 0)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cycle_health").fetchone()[0], 0)

    def test_explicit_legacy_cli_remains_supported(self):
        process = self.invoke("--state", "SUCCESS", "--exit-status", "0")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["row"]["health_state"], "SUCCESS")

    def test_packaged_hooks_preserve_result_and_use_exact_instance_name(self):
        for unit in ("rackmarshal-domain@.service", "rackmarshal-self-watch.service"):
            hook = Path("packaging/systemd") / (unit + ".d") / "20-cycle-health.conf"
            self.assertIn("ExecStopPost=-/opt/rackmarshal/venv/bin/python -m rackmarshal.selfwatch.cycle_health --unit %n --from-systemd", hook.read_text())
            self.assertNotIn("ReadWritePaths", hook.read_text())
        self.assertIn("cp -R packaging/systemd/*", Path("scripts/build-installer-bundle.sh").read_text())
        self.assertIn('systemctl cat "$unit"', Path("scripts/install.sh").read_text())
