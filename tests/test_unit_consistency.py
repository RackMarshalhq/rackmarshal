import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT_DIR = ROOT / "packaging" / "systemd"


def unit_files():
    return sorted(p.name for p in UNIT_DIR.iterdir() if p.is_file())


class UnitConsistency(unittest.TestCase):
    """Every shipped unit must be installed, bundled and removed; none may be forgotten."""

    def test_bootstrap_bundles_every_unit(self):
        text = (ROOT / "scripts" / "bootstrap-wheel.py").read_text()
        bundled = set(re.search(r"^UNITS = \((.*?)\)$", text, re.M | re.S).group(1).replace("'", "").replace(" ", "").split(","))
        bundled -= {""}
        shipped = set(unit_files()) | {f"rackmarshal-domain@.service.d/20-cycle-health.conf",
                                       "rackmarshal-self-watch.service.d/20-cycle-health.conf"}
        self.assertEqual(bundled, shipped)

    def test_installer_installs_and_uninstaller_removes_every_top_level_unit(self):
        install = (ROOT / "scripts" / "install.sh").read_text()
        uninstall = (ROOT / "scripts" / "uninstall.sh").read_text()
        for name in unit_files():
            self.assertIn(name, install, f"install.sh does not install {name}")
            self.assertIn(name, uninstall, f"uninstall.sh does not remove {name}")

    def test_prune_timer_is_enabled_and_checked(self):
        install = (ROOT / "scripts" / "install.sh").read_text()
        self.assertRegex(install, r"systemctl enable --now [^\n]*rackmarshal-observation-prune\.timer")
        self.assertIn("systemctl is-active --quiet rackmarshal-observation-prune.timer", install)

    def test_prune_service_runs_the_prune_module(self):
        service = (UNIT_DIR / "rackmarshal-observation-prune.service").read_text()
        self.assertIn("-m rackmarshal.maintenance.prune", service)
        self.assertIn("ReadWritePaths=/var/lib/rackmarshal", service)
        timer = (UNIT_DIR / "rackmarshal-observation-prune.timer").read_text()
        self.assertIn("Unit=rackmarshal-observation-prune.service", timer)


if __name__ == "__main__":
    unittest.main()
