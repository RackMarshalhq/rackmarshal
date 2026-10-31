import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT = (ROOT / "packaging/systemd/optional/rackmarshal-mcp.service").read_text()


class McpUnit(unittest.TestCase):
    def test_runs_the_installed_entry_point_as_service_user(self):
        self.assertIn("ExecStart=/opt/rackmarshal/venv/bin/rackmarshal-mcp\n", UNIT)
        self.assertIn("User=rackmarshal\n", UNIT)
        self.assertIn("rackmarshal-mcp", (ROOT / "pyproject.toml").read_text())

    def test_hardened_and_writes_only_to_state_and_log(self):
        for line in ("NoNewPrivileges=true", "PrivateTmp=true", "ProtectSystem=strict", "ProtectHome=true"):
            self.assertIn(line, UNIT)
        self.assertIn("ReadWritePaths=/var/lib/rackmarshal /var/log/rackmarshal\n", UNIT)

    def test_no_credentials_or_public_binding_in_unit(self):
        self.assertIsNone(re.search(r"(?i)token|secret|password|api[_-]?key|0\.0\.0\.0|EnvironmentFile", UNIT))

    def test_documented(self):
        self.assertIn("rackmarshal-mcp.service", (ROOT / "CONFIGURATION.md").read_text())
        self.assertIn("rackmarshal-mcp.service", (ROOT / "scripts/uninstall.sh").read_text())
        self.assertIn("rackmarshal-mcp.service", (ROOT / "scripts/bootstrap-wheel.py").read_text())


if __name__ == "__main__":
    unittest.main()
