"""Execute each runner's real delivery argv against a disposable empty queue."""
from contextlib import closing
import ast
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class CycleDeliveryCommands(unittest.TestCase):
    def test_cycle_locks_use_the_writable_state_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            configuration = {
                "STATE_DB": str(root / "state.db"),
                "SITE_NAME": "fixture", "HARDWARE_HOT_THRESHOLD_C": "80",
                "HARDWARE_HOT_REQUIRED_SAMPLES": "2", "HARDWARE_URGENT_THRESHOLD_C": "90",
                "HARDWARE_RECOVERY_THRESHOLD_C": "70", "HARDWARE_RECOVERY_REQUIRED_SAMPLES": "2",
            }
            config.write_text(chr(10).join(k + "=" + v for k, v in configuration.items()))
            for domain in ("ha", "zfs", "hardware"):
                code = (
                    "import fcntl; from rackmarshal.domains." + domain + ".cycle import LOCK_FILE; "
                    "LOCK_FILE.parent.mkdir(parents=True,exist_ok=True); "
                    "handle=LOCK_FILE.open('w'); "
                    "fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB); "
                    "print(LOCK_FILE); handle.close()"
                )
                result = subprocess.run([sys.executable, "-c", code], text=True,
                                        capture_output=True, timeout=10,
                                        env=dict(os.environ, RACKMARSHAL_CONFIG=str(config),
                                                 RACKMARSHAL_STATE_DB=str(root / "state.db")))
                with self.subTest(domain=domain):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(Path(result.stdout.strip()),
                                     root / "locks" / ("rackmarshal-" + domain + "-cycle.lock"))
                    self.assertTrue(Path(result.stdout.strip()).is_file())

    def test_packaged_ha_and_hardware_processors_execute_without_script_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "state.db"
            config = root / "config"
            configuration = {
                "STATE_DB": str(database), "VENV_PYTHON": sys.executable,
                "INSTALL_ROOT": str(Path.cwd()),
                "SITE_NAME": "fixture", "HARDWARE_HOT_THRESHOLD_C": "80",
                "HARDWARE_HOT_REQUIRED_SAMPLES": "2", "HARDWARE_URGENT_THRESHOLD_C": "90",
                "HARDWARE_RECOVERY_THRESHOLD_C": "70", "HARDWARE_RECOVERY_REQUIRED_SAMPLES": "2",
            }
            config.write_text(chr(10).join(k + "=" + v for k, v in configuration.items()))
            environment = dict(os.environ, RACKMARSHAL_CONFIG=str(config), RACKMARSHAL_STATE_DB=str(database))
            migration = subprocess.run([sys.executable, "-m", "rackmarshal.db.migrations.migrate",
                                        "--db", str(database), "--apply", "--yes"],
                                       env=environment, text=True, capture_output=True, timeout=10)
            self.assertEqual(migration.returncode, 0, migration.stderr)
            with closing(sqlite3.connect(database)) as connection:
                payload = json.dumps({"resources": [{"resource_key": "fictional", "resource_type": "entity", "status": "on"}]})
                connection.execute("INSERT INTO observations(collector,observed_at,source,schema_version,tls_verified,resource_count,payload_json) VALUES('home_assistant','2026-01-01T00:00:00Z','fixture',1,1,1,?)", (payload,))
                connection.execute("INSERT INTO ha_resource_baseline(resource_key,resource_type,display_name,baseline_state,expected_status,source_observation_id) VALUES('fictional','entity','Fixture','VERIFIED','on',1)")
                connection.commit()
            result = subprocess.run([sys.executable, "-m", "rackmarshal.domains.ha.incidents",
                                     "--db", str(database), "--bootstrap-observation", "1"],
                                    env=environment, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["processing_kind"], "BOOTSTRAP")
            with closing(sqlite3.connect(database)) as connection:
                for number in (2, 3):
                    connection.execute("INSERT INTO observations(collector,observed_at,source,schema_version,tls_verified,resource_count,payload_json) VALUES('home_assistant',?,'fixture',1,1,1,?)", ("2026-01-01T00:0" + str(number) + ":00Z", payload))
                connection.commit()
            code = ("import json; from rackmarshal.domains.ha.cycle import process_through_observation; "
                    "print(json.dumps(process_through_observation(3)))")
            result = subprocess.run([sys.executable, "-c", code], env=environment,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            caught_up = json.loads(result.stdout)
            self.assertEqual(caught_up["observation_id"], 3)
            self.assertEqual(caught_up["observations_processed"], 2)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM ha_incident_processing").fetchone()[0], 3)
            code = ("import json; from rackmarshal.domains.hardware.cycle import process_hardware_incidents_ledger; "
                    "print(json.dumps(process_hardware_incidents_ledger()))")
            result = subprocess.run([sys.executable, "-c", code], env=environment,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.splitlines()[-1])["consumer"], "hardware_incident_processor")

    def test_all_runner_commands_execute_delivery_without_external_effects(self):
        runners = list(Path("rackmarshal/domains").glob("*/cycle.py")) + [Path("rackmarshal/selfwatch/cycle.py")]
        exercised = set()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "state.db"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE incident_notifications(id INTEGER PRIMARY KEY,delivery_state TEXT)")
            credential = root / "ha.env"
            credential.write_text('HA_URL=http://127.0.0.1:1\nHA_TOKEN=fictional-test-token\n')
            config = root / "config"
            config.write_text("STATE_DB=" + str(database) + '\nLOCAL_AI_ENABLED=false\n')
            for runner in runners:
                tree = ast.parse(runner.read_text())
                calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                         and node.args and isinstance(node.args[0], ast.BinOp)
                         and isinstance(node.args[0].left, ast.Name)
                         and node.args[0].left.id == "DELIVERY_WORKER"]
                self.assertEqual(len(calls), 1, str(runner))
                scope = {"DELIVERY_WORKER": [sys.executable, "-m", "rackmarshal.notifications.delivery"],
                         "DB": str(database), "HA_CREDENTIAL": str(credential),
                         "INCIDENT_EXPLAINER": [sys.executable, "-m", "rackmarshal.incidents.explain"]}
                argv = eval(compile(ast.Expression(calls[0].args[0]), str(runner), "eval"), scope)
                with self.subTest(runner=str(runner)):
                    self.assertTrue(all(isinstance(value, str) for value in argv), argv)
                    completed = subprocess.run(argv, text=True, capture_output=True, timeout=10,
                                               env=dict(os.environ, RACKMARSHAL_CONFIG=str(config)))
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    result = json.loads(completed.stdout)
                    self.assertEqual(result["worker"], "incident_notification_delivery_worker")
                    self.assertEqual(result["rows_scanned"], 0)
                    self.assertEqual(result["sent"], 0)
                    self.assertEqual(result["failed"], 0)
                exercised.add(str(runner))
        self.assertEqual(len(exercised), 7)


if __name__ == "__main__":
    unittest.main()
