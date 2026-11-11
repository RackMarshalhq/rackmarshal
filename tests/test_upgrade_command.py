from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

from rackmarshal import cli
from rackmarshal.maintenance import upgrade_apply as ua
from tests.test_upgrade_plan import MIGRATION_A, record_text, wheel_files


class UpgradeCommandTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.site = self.root / "site"
        files, dist = wheel_files("1.3.0rc1", {"001": MIGRATION_A})
        for name, body in files.items():
            path = self.site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        (self.site / dist).mkdir(exist_ok=True)
        (self.site / dist / "RECORD").write_text(record_text(files, dist))
        self.db = self.root / "state.db"
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TABLE schema_migrations(id TEXT PRIMARY KEY, checksum TEXT)")
            c.execute("INSERT INTO schema_migrations VALUES('001',?)", (hashlib.sha256(MIGRATION_A).hexdigest(),))
            c.commit()
        self.bundle = self.root / "bundle"
        (self.bundle / "scripts").mkdir(parents=True)
        (self.bundle / "scripts/lifecycle.py").write_text("# fixture\n")
        self.previous = self.root / "rackmarshal-1.3.0rc1-py3-none-any.whl"
        self.previous.write_bytes(b"previous wheel")
        self.wheel = self.make_bundle_wheel("1.3.1", {"001": MIGRATION_A})
        self.wheel_sha = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        self.output = []
        self.calls = []

    def make_bundle_wheel(self, version, migrations):
        files, dist = wheel_files(version, migrations, b"print('new')\n")
        record = record_text(files, dist)
        path = self.bundle / ("rackmarshal-%s-py3-none-any.whl" % version)
        with zipfile.ZipFile(path, "w") as z:
            for n, b in files.items():
                z.writestr(n, b)
            z.writestr(dist + "/RECORD", record)
        return path

    def runner(self, command, **kwargs):
        self.calls.append(command)
        return SimpleNamespace(returncode=self.child_status)

    child_status = 0

    def go(self, **kw):
        args = dict(site_packages=self.site, database=self.db, bundle=self.bundle, previous_wheel=self.previous,
                    previous_sha256="a" * 64, wheel_sha256=self.wheel_sha, runner=self.runner, out=self.output.append)
        args.update(kw)
        return ua.run(**args)

    def text(self):
        return "\n".join(self.output)

    def test_default_run_is_a_plan_and_runs_nothing(self):
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.calls, [])
        self.assertIn("Nothing was changed", self.text())
        self.assertIn("/usr/bin/python3 -I -B -S", self.text())

    def test_apply_runs_the_bundle_script_with_the_trusted_interpreter(self):
        self.assertEqual(self.go(apply=True, note="fix", is_root=True, verify_timeout=900), 0)
        self.assertEqual(self.calls, [["/usr/bin/python3", "-I", "-B", "-S", str(self.bundle / "scripts/lifecycle.py"), "upgrade",
                                       "--previous-wheel", str(self.previous), "--previous-sha256", "a" * 64,
                                       "--verify-timeout", "900"]])
        self.assertIn("COMMITTED", self.text())

    def test_apply_needs_root_and_a_note(self):
        with self.assertRaisesRegex(ua.UpgradeRefused, "as root"):
            self.go(apply=True, note="why", is_root=False)
        with self.assertRaisesRegex(ua.UpgradeRefused, "--note"):
            self.go(apply=True, note="  ", is_root=True)
        self.assertEqual(self.calls, [])

    def test_child_failure_status_is_returned_with_guidance(self):
        self.child_status = 1
        self.assertEqual(self.go(apply=True, note="why", is_root=True), 1)
        self.assertIn("HEALTH CHECK FAILED", self.text())

    def test_a_plan_that_is_not_ready_never_applies(self):
        (self.site / "rackmarshal/__init__.py").write_bytes(b"hand patch\n")
        self.assertEqual(self.go(apply=True, note="why", is_root=True), 2)
        self.assertEqual(self.calls, [])
        self.assertIn("hand patch", self.text())

    def test_database_changes_are_not_applied(self):
        self.wheel = self.make_bundle_wheel("1.3.2", {"001": MIGRATION_A, "002": b"CREATE TABLE b(x);\n"})
        (self.bundle / "rackmarshal-1.3.1-py3-none-any.whl").unlink()
        sha = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        self.assertEqual(self.go(apply=True, note="why", is_root=True, wheel_sha256=sha), 2)
        self.assertEqual(self.calls, [])

    def test_wrong_wheel_checksum_is_refused(self):
        with self.assertRaises(ua.upgrade_plan.PlanError):
            self.go(wheel_sha256="0" * 64)

    def test_bundle_and_previous_wheel_problems_are_explained(self):
        with self.assertRaisesRegex(ua.UpgradeRefused, "not an extracted"):
            self.go(bundle=self.root / "nowhere")
        with self.assertRaisesRegex(ua.UpgradeRefused, "previous release's wheel"):
            self.go(previous_wheel=self.root / "missing.whl")
        self.make_bundle_wheel("1.3.3", {"001": MIGRATION_A})
        with self.assertRaisesRegex(ua.UpgradeRefused, "exactly one"):
            self.go()

    def test_command_is_registered(self):
        args = cli._build_parser().parse_args(
            ["upgrade", "--bundle", "b", "--wheel-sha256", "x", "--previous-wheel", "p", "--previous-sha256", "y"])
        self.assertEqual((args.cmd, args.apply, args.verify_timeout), ("upgrade", False, 1800))
        self.assertEqual(cli.COMMANDS["upgrade"].__name__, "_cmd_upgrade")


if __name__ == "__main__":
    unittest.main()
