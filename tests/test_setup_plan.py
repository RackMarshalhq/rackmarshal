import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from rackmarshal.cli import main
from rackmarshal.core.setup import setup_plan
from rackmarshal.ui.dashboard import collection_data, render_incident_index
from rackmarshal.ui.incidents import render_incident_page
from tests.test_api_v11_timeline import ApiV11Timeline


class SetupPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = self.root / "config"
    def tearDown(self):
        self.tmp.cleanup()
    def plan(self, text):
        self.config.write_text(text)
        return setup_plan(self.config)
    def test_base_install_does_not_imply_monitoring(self):
        p = self.plan("STATE_DB=/nonexistent/state.db\n")
        self.assertEqual(p["configuration_status"], "VALID")
        self.assertTrue(all(d["setup_state"] == "DISABLED" for d in p["domains"]))
        self.assertIn("Choose one supported domain", p["next_steps"][0])
    def test_missing_required_files_block_even_when_keys_present(self):
        p = self.plan("STATE_DB=/nonexistent/state.db\nENABLED_DOMAINS=pve\nPVE_API_ENV=/nonexistent/auth\nPVE_CA_FILE=/nonexistent/ca\n")
        d = p["domains"][0]
        self.assertEqual(d["setup_state"], "NEEDS_CONFIGURATION")
        self.assertEqual(d["file_checks"]["PVE_API_ENV"], "MISSING")
        self.assertEqual(p["configuration_status"], "INVALID")
    def test_file_permissions_and_no_secret_values_or_probes(self):
        token = "private-token-value-do-not-emit"
        credential = self.root / "secret-auth"
        ca = self.root / "private-ca"
        credential.write_text(token); ca.write_text("certificate")
        credential.chmod(0o600); ca.chmod(0o600)
        content = f"STATE_DB=/uncreated/state.db\nENABLED_DOMAINS=pve\nPVE_API_ENV={credential}\nPVE_CA_FILE={ca}\nSITE_NAME={token}\n"
        self.config.write_text(content)
        before = {f.name:f.read_bytes() for f in self.root.iterdir()}
        with patch("urllib.request.urlopen", side_effect=AssertionError("network probe")), patch("subprocess.run", side_effect=AssertionError("service action")):
            p = setup_plan(self.config)
        self.assertEqual(p["domains"][0]["setup_state"], "CONFIGURATION_COMPLETE")
        encoded = json.dumps(p)
        self.assertNotIn(token, encoded); self.assertNotIn(str(self.root), encoded)
        self.assertEqual(before, {f.name:f.read_bytes() for f in self.root.iterdir()})
        credential.chmod(0o644)
        self.assertEqual(setup_plan(self.config)["domains"][0]["file_checks"]["PVE_API_ENV"], "PERMISSIONS_TOO_BROAD")
    def test_unknown_domain_never_creates_supported_coverage(self):
        p = self.plan("STATE_DB=/absent/db\nENABLED_DOMAINS=aircraft-engine\n")
        self.assertEqual(p["configuration_status"], "INVALID")
        self.assertTrue(all(not d["enabled"] for d in p["domains"]))
        self.assertNotIn("aircraft-engine", json.dumps(p))
    def test_missing_config_reports_generic_error_and_exit_two(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = main(["setup-plan", "--config", str(self.root / "absent-private-path")])
        self.assertEqual(rc, 2)
        self.assertNotIn("absent-private-path", out.getvalue())
        self.assertEqual(json.loads(out.getvalue())["configuration_status"], "INVALID")


class CoverageSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fx = ApiV11Timeline(); self.fx.setUp(); self.db = self.fx.db
    def tearDown(self):
        self.fx.tearDown()
    def test_disabled_observations_remain_historical_and_do_not_hide_incidents(self):
        p = render_incident_index(self.db, enabled_domains=[])
        self.assertIn("Disabled in configuration", p)
        self.assertIn("Historical records only; collection is disabled.", p)
        self.assertIn("/incidents/BACKUP:1", p)
        self.assertIn("general network monitoring", p)
    def test_unknown_selection_is_not_enabled_or_disabled(self):
        data = collection_data(self.db)
        self.assertTrue(all(d["enabled"] is None for d in data["domains"]))
        self.assertIn("Domain selection unavailable", render_incident_index(self.db))
    def test_selection_normalizes_case_and_space_without_health_claim(self):
        data = collection_data(self.db, enabled_domains=[" backup "])
        self.assertTrue(next(d for d in data["domains"] if d["domain"]=="BACKUP")["enabled"])
        self.assertFalse(next(d for d in data["domains"] if d["domain"]=="PVE")["enabled"])
        p = render_incident_page(self.db, "BACKUP:1", enabled_domains=[])
        self.assertIn("Historical records only", p)

if __name__ == "__main__":
    unittest.main()
