import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("status_acl", ROOT / "scripts" / "status-acl.py")
acl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acl)


class Render(unittest.TestCase):
    def test_lists_callers_and_drops_the_rest(self):
        text = acl.render(9110, ["192.0.2.10", "192.0.2.0/28"])
        self.assertIn('iifname "lo" accept', text)
        self.assertIn("tcp dport 9110 ip saddr { 192.0.2.0/28, 192.0.2.10 } accept", text)
        self.assertIn("tcp dport 9110 counter drop", text)
        # the accept rules come before the drop rule
        self.assertLess(text.index("ip saddr"), text.index("counter drop"))
        self.assertIn("policy accept", text)

    def test_ipv6_and_deduplication(self):
        text = acl.render(9110, ["fd00::1", "fd00::1", "192.0.2.10", "192.0.2.10"])
        self.assertIn("ip6 saddr { fd00::1 } accept", text)
        self.assertEqual(text.count("192.0.2.10"), 1)

    def test_custom_port(self):
        text = acl.render(8080, ["192.0.2.10"])
        self.assertIn("tcp dport 8080", text)
        self.assertNotIn("9110", text.split("\n", 1)[1])

    def test_refuses_everyone_and_nothing(self):
        for bad in (["0.0.0.0/0"], ["::/0"], [], [""]):
            with self.assertRaises(ValueError, msg=str(bad)):
                acl.render(9110, bad)

    def test_refuses_injection_and_malformed_input(self):
        for bad in ("192.0.2.1 } accept; tcp dport 22 drop #", "192.0.2.1,192.0.2.2", "192.0.2.5/24",
                    "host.example", "192.0.2.1\n192.0.2.2", '1.1.1.1"', "{1.1.1.1}", "999.1.1.1"):
            with self.assertRaises(ValueError, msg=bad):
                acl.render(9110, [bad])

    def test_refuses_bad_port(self):
        for bad in (0, 65536, -1, True, "9110"):
            with self.assertRaises(ValueError):
                acl.render(bad, ["192.0.2.1"])

    @unittest.skipUnless(shutil.which("nft"), "nft not installed")
    def test_nft_accepts_the_generated_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "acl.nft"
            path.write_text(acl.render(9110, ["192.0.2.10", "192.0.2.0/28", "fd00::/64"]))
            result = subprocess.run(["nft", "-c", "-f", str(path)], capture_output=True, text=True)
            if "Operation not permitted" in result.stderr:
                self.skipTest("nft check needs privileges")
            self.assertEqual(result.returncode, 0, result.stderr)


class Packaging(unittest.TestCase):
    def test_unit_checks_the_file_before_replacing_the_table(self):
        unit = (ROOT / "packaging" / "systemd" / "optional" / "rackmarshal-status-acl.service").read_text()
        self.assertLess(unit.index("nft -c -f"), unit.index("delete table"))
        self.assertIn("ExecStop=-/usr/sbin/nft delete table inet rm_status_acl", unit)

    def test_installer_does_not_enable_it(self):
        self.assertNotIn("status-acl", (ROOT / "scripts" / "install.sh").read_text())

    def test_uninstaller_removes_it(self):
        self.assertIn("rackmarshal-status-acl.service", (ROOT / "scripts" / "uninstall.sh").read_text())


if __name__ == "__main__":
    unittest.main()
