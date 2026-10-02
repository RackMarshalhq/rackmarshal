"""Regression cases for read-only setup across every supported domain."""
import contextlib
import io
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rackmarshal.cli import main
from rackmarshal.core.setup import setup_plan
from rackmarshal.ui.dashboard import collection_data, render_incident_index
from tests import test_api_v11_timeline as fixtures


class SetupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.secret = self.root / "credentials"
        self.secret.write_text("fixture-private-contents")
        self.secret.chmod(0o600)
        # Explicit examples keep this independent of the implementation's
        # DOMAIN_REQUIREMENTS and catch accidentally removed requirements.
        self.values = {
            "STATE_DB": str(self.root / "uncreated" / "state.db"),
            "PVE_API_ENV": str(self.secret), "PVE_CA_FILE": str(self.secret),
            "PBS_API_ENV": str(self.secret), "PBS_CA_FILE": str(self.secret),
            "PVE_NODE": "fixture-node", "HA_CREDENTIAL_FILE": str(self.secret),
            "SITE_NAME": "fixture-site",
            "HARDWARE_NVME_SERIALS": "fixture-serial",
            "HARDWARE_NVME_fixture-serial_MODEL": "fixture-model",
            "HARDWARE_NVME_fixture-serial_ROLE": "fixture-role",
            "HARDWARE_HOT_THRESHOLD_C": "60", "HARDWARE_HOT_REQUIRED_SAMPLES": "3",
            "HARDWARE_URGENT_THRESHOLD_C": "80", "HARDWARE_RECOVERY_THRESHOLD_C": "50",
            "HARDWARE_RECOVERY_REQUIRED_SAMPLES": "3",
            "MOUNT_CATALOG_FILE": str(self.secret),
        }
        for prefix in ("ZFS", "HARDWARE", "MOUNT"):
            self.values.update({f"{prefix}_SSH_HOST": "fixture.invalid",
                                f"{prefix}_SSH_USER": "fixture-user",
                                f"{prefix}_SSH_KEY": str(self.secret),
                                f"{prefix}_KNOWN_HOSTS": str(self.secret)})

    def plan(self, domains, omit=()):
        values = dict(self.values, ENABLED_DOMAINS=domains)
        self.config.write_text("".join(f"{key}={value}\n" for key, value in values.items()
                                       if key not in omit))
        return setup_plan(self.config)

    def domain(self, report, name):
        return next(item for item in report["domains"] if item["domain"] == name.upper())

    def test_all_supported_domains_complete_without_reading_credentials_or_creating_database(self):
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path == self.secret:
                raise AssertionError("setup read credential contents")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", guarded_open), \
                patch("socket.create_connection", side_effect=AssertionError("network access")), \
                patch("subprocess.Popen", side_effect=AssertionError("process launch")):
            for domain in ("pve", "zfs", "backup", "ha", "hardware", "mount"):
                with self.subTest(domain=domain):
                    report = self.plan(domain)
                    self.assertEqual(report["configuration_status"], "VALID")
                    self.assertEqual([row["domain"] for row in report["domains"] if row["enabled"]],
                                     [domain.upper()])
                    self.assertTrue(all(row["setup_state"] == "DISABLED"
                                        for row in report["domains"] if not row["enabled"]))
                    self.assertEqual(self.domain(report, domain)["setup_state"], "CONFIGURATION_COMPLETE")
                    self.assertTrue(report["read_only"])
                    self.assertEqual(report["authority"], "DERIVED")
                    encoded = json.dumps(report)
                    for private in (str(self.root), "fixture-serial", "fixture.invalid", "fixture-private-contents"):
                        self.assertNotIn(private, encoded)
        self.assertFalse((self.root / "uncreated").exists())
        self.assertEqual(self.secret.read_text(), "fixture-private-contents")
        self.assertEqual(self.secret.stat().st_mode & 0o777, 0o600)

    def test_domain_specific_missing_configuration_blocks_readiness(self):
        cases = {"pve": "PVE_CA_FILE", "zfs": "ZFS_KNOWN_HOSTS", "backup": "PBS_API_ENV",
                 "ha": "HA_CREDENTIAL_FILE", "hardware": "HARDWARE_RECOVERY_REQUIRED_SAMPLES",
                 "mount": "MOUNT_CATALOG_FILE"}
        for domain, key in cases.items():
            with self.subTest(domain=domain):
                report = self.plan(domain, omit=(key,))
                self.assertEqual(report["configuration_status"], "INVALID")
                row = self.domain(report, domain)
                self.assertEqual(row["setup_state"], "NEEDS_CONFIGURATION")
                self.assertIn(key, row["missing_keys"])

    def test_missing_hardware_identity_metadata_is_blocking_and_redacted(self):
        report = self.plan("hardware", omit=("HARDWARE_NVME_fixture-serial_MODEL",))
        self.assertEqual(report["configuration_status"], "INVALID")
        self.assertEqual(self.domain(report, "hardware")["setup_state"], "NEEDS_CONFIGURATION")
        self.assertNotIn("fixture-serial", json.dumps(report))

    def test_directory_is_not_a_ready_credential(self):
        directory = self.root / "directory"
        directory.mkdir(mode=0o700)
        self.values["HA_CREDENTIAL_FILE"] = str(directory)
        report = self.plan("ha")
        self.assertEqual(report["configuration_status"], "INVALID")
        self.assertEqual(self.domain(report, "ha")["file_checks"]["HA_CREDENTIAL_FILE"], "NOT_A_FILE")

    def test_unreadable_file_does_not_imply_readiness(self):
        with patch("rackmarshal.core.setup.os.access", return_value=False):
            report = self.plan("ha")
        self.assertEqual(report["configuration_status"], "INVALID")
        self.assertEqual(self.domain(report, "ha")["file_checks"]["HA_CREDENTIAL_FILE"], "UNREADABLE")

    def test_group_or_other_permissions_block_credentials(self):
        for mode in (0o640, 0o620, 0o610, 0o604, 0o602, 0o601):
            with self.subTest(mode=oct(mode)):
                self.secret.chmod(mode)
                report = self.plan("ha")
                self.assertEqual(report["configuration_status"], "INVALID")
                self.assertEqual(self.domain(report, "ha")["setup_state"], "NEEDS_CONFIGURATION")

    def test_disabled_domain_has_no_readiness_claim_for_missing_files(self):
        self.values["HA_CREDENTIAL_FILE"] = str(self.root / "absent")
        report = self.plan("")
        self.assertEqual(report["configuration_status"], "VALID")
        self.assertEqual(self.domain(report, "ha")["setup_state"], "DISABLED")
        self.assertEqual(self.domain(report, "ha")["file_checks"], {})

    def test_missing_state_database_setting_blocks_overall_validity(self):
        report = self.plan("ha", omit=("STATE_DB",))
        self.assertEqual(report["configuration_status"], "INVALID")
        self.assertFalse(report["state_database_configured"])

    def test_mixed_selection_normalizes_and_retains_unsupported_warning(self):
        report = self.plan(" HA ,ha, , unsupported-fixture ")
        self.assertEqual(report["configuration_status"], "INVALID")
        self.assertEqual([row["domain"] for row in report["domains"] if row["enabled"]], ["HA"])
        self.assertNotIn("unsupported-fixture", json.dumps(report))

    def test_invalid_encoding_returns_structured_cli_error_without_path(self):
        self.config.write_bytes(b"STATE_DB=\xff\n")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = main(["setup-plan", "--config", str(self.config)])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())["configuration_status"], "INVALID")
        self.assertNotIn(str(self.root), output.getvalue())


class CoverageSafetyTests(unittest.TestCase):
    def test_enabled_domain_without_observations_has_no_health_or_cycle_claim(self):
        with contextlib.closing(sqlite3.connect(":memory:")) as database:
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA query_only=ON")
            rows = collection_data(database, enabled_domains=["mount"])["domains"]
            mount = next(row for row in rows if row["domain"] == "MOUNT")
            self.assertTrue(mount["enabled"])
            self.assertIsNone(mount["observation"])
            self.assertIsNone(mount["cycle"])
            self.assertIsNone(mount["freshness"])
            page = render_incident_index(database, enabled_domains=["mount"])
            self.assertIn("Selection alone does not prove active collection", page)
            self.assertIn("Observation not recorded", page)
            self.assertNotIn("Recorded success", page)
            self.assertNotIn("Fresh observation</strong>", page)

    def test_selection_and_freshness_never_rewrite_retained_lifecycle(self):
        fixture = fixtures.ApiV11Timeline()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        database = fixture.db
        before = list(database.iterdump())
        database.execute("PRAGMA query_only=ON")
        for selected in (None, [], ["backup"]):
            for freshness in ("OK", "STALE", "MISSING"):
                with self.subTest(selected=selected, freshness=freshness):
                    def build(observations, now=None):
                        return {"BACKUP": {"state": freshness, "stale_after_seconds": 900}}
                    page = render_incident_index(database, freshness_builder=build,
                                                 enabled_domains=selected)
                    # The fixture has both open and recovered incidents. Neither
                    # selection nor a fresh observation grants lifecycle authority.
                    rows = re.findall(r"<tr>(.*?)</tr>", page, flags=re.DOTALL)
                    for incident_id, state in (("BACKUP:1", "RECOVERED"),
                                               ("PVE:2", "OPEN"), ("HARDWARE:3", "OPEN")):
                        matching = [row for row in rows if f"href='/incidents/{incident_id}'" in row]
                        self.assertEqual(len(matching), 1)
                        self.assertIn(f"class='badge {state}'>{state}</span>", matching[0])
                        if state == "OPEN":
                            self.assertNotIn("Recovered:", matching[0])
                        else:
                            self.assertIn("Recovered:", matching[0])
                    self.assertIn('data-freshness="' + freshness + '"', page)
                    self.assertIn("Fresh observations do not prove a cycle completed successfully or an incident recovered", page)
                    if selected == []:
                        self.assertIn("Historical records only; collection is disabled", page)
                    self.assertEqual(list(database.iterdump()), before)


if __name__ == "__main__":
    unittest.main()
