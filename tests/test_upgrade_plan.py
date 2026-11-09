import base64
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from rackmarshal import cli
from rackmarshal.maintenance import upgrade_plan as up

MIGRATION_A = b"CREATE TABLE a(x);\n"
MIGRATION_B = b"CREATE TABLE b(x);\n"


def rec_hash(data):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def wheel_files(version, migrations, code=b"print('code')\n"):
    files = {"rackmarshal/__init__.py": code}
    for name, body in migrations.items():
        files["rackmarshal/db/migrations/%s.sql" % name] = body
    dist = "rackmarshal-%s.dist-info" % version
    files[dist + "/METADATA"] = ("Metadata-Version: 2.1\nName: rackmarshal\nVersion: %s\n" % version).encode()
    return files, dist


def record_text(files, dist):
    rows = ["%s,%s,%d" % (n, rec_hash(b), len(b)) for n, b in files.items()]
    return "\n".join(rows + ["%s/RECORD,," % dist]) + "\n"


class UpgradePlanTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.site = self.root / "site"
        self.install("1.3.0rc1", {"001": MIGRATION_A})
        self.db = self.root / "state.db"
        self.set_ledger({"001": MIGRATION_A})

    def install(self, version, migrations, code=b"print('code')\n"):
        files, dist = wheel_files(version, migrations, code)
        for name, body in files.items():
            path = self.site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        (self.site / dist).mkdir(exist_ok=True)
        (self.site / dist / "RECORD").write_text(record_text(files, dist))

    def set_ledger(self, migrations):
        self.db.unlink(missing_ok=True)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TABLE schema_migrations(id TEXT PRIMARY KEY, checksum TEXT)")
            for name, body in migrations.items():
                c.execute("INSERT INTO schema_migrations VALUES(?,?)", (name, hashlib.sha256(body).hexdigest()))
            c.commit()

    def make_wheel(self, version, migrations, name=None, tamper=False):
        files, dist = wheel_files(version, migrations, b"print('new')\n")
        record = record_text(files, dist)
        if tamper:
            files["rackmarshal/__init__.py"] = b"print('evil')\n"
        path = self.root / (name or "rackmarshal-%s-py3-none-any.whl" % version)
        with zipfile.ZipFile(path, "w") as z:
            for n, b in files.items():
                z.writestr(n, b)
            z.writestr(dist + "/RECORD", record)
        sums = self.root / "SHA256SUMS"
        sums.write_text("%s  %s\n" % (hashlib.sha256(path.read_bytes()).hexdigest(), path.name))
        return path, sums

    def plan(self, wheel, sums=None, sha=None):
        return up.plan(self.site, self.db, wheel, sums, sha)

    def test_same_schema_newer_release_is_ready(self):
        wheel, sums = self.make_wheel("1.3.1", {"001": MIGRATION_A})
        result = self.plan(wheel, sums)
        self.assertEqual(result["status"], "READY", result)
        self.assertFalse(result["changes_made"])
        self.assertIn("match release 1.3.0rc1 exactly", up.describe(result))

    def test_hand_patched_install_is_refused_with_the_file_name(self):
        (self.site / "rackmarshal/__init__.py").write_bytes(b"print('hand patch')\n")
        wheel, sums = self.make_wheel("1.3.1", {"001": MIGRATION_A})
        result = self.plan(wheel, sums)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("rackmarshal/__init__.py", result["refusals"][0])

    def test_missing_installed_file_is_refused(self):
        (self.site / "rackmarshal/__init__.py").unlink()
        wheel, sums = self.make_wheel("1.3.1", {"001": MIGRATION_A})
        self.assertIn("missing", self.plan(wheel, sums)["refusals"][0])

    def test_extra_migration_needs_database_change(self):
        wheel, sums = self.make_wheel("1.3.1", {"001": MIGRATION_A, "002": MIGRATION_B})
        result = self.plan(wheel, sums)
        self.assertEqual(result["status"], "NEEDS_DATABASE_CHANGE")
        self.assertIn("002", up.describe(result))

    def test_different_history_is_refused(self):
        self.set_ledger({"001": b"something else\n"})
        wheel, sums = self.make_wheel("1.3.1", {"001": MIGRATION_A})
        self.assertEqual(self.plan(wheel, sums)["status"], "REFUSED")

    def test_old_or_same_or_foreign_series_is_refused(self):
        for version in ("1.3.0rc1", "1.3.0rc0", "1.2.9", "2.0.0"):
            wheel, sums = self.make_wheel(version, {"001": MIGRATION_A})
            self.assertEqual(self.plan(wheel, sums)["status"], "REFUSED", version)

    def test_release_candidate_sorts_before_final(self):
        self.assertLess(up.parse_version("1.3.0rc1"), up.parse_version("1.3.0"))
        self.assertLess(up.parse_version("1.3.0"), up.parse_version("1.3.1rc1"))
        with self.assertRaises(up.PlanError):
            up.parse_version("1.3.0.dev2")

    def test_wrong_checksum_is_refused(self):
        wheel, sums = self.make_wheel("1.3.1", {"001": MIGRATION_A})
        sums.write_text("%s  %s\n" % ("0" * 64, wheel.name))
        with self.assertRaisesRegex(up.PlanError, "does not match the checksum file"):
            self.plan(wheel, sums)
        with self.assertRaisesRegex(up.PlanError, "you supplied"):
            self.plan(wheel, sha="1" * 64)

    def test_checksum_is_required_and_supplied_checksum_works(self):
        wheel, sums = self.make_wheel("1.3.1", {"001": MIGRATION_A})
        with self.assertRaisesRegex(up.PlanError, "--sums"):
            self.plan(wheel)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        self.assertEqual(self.plan(wheel, sha=digest)["status"], "READY")
        both = self.plan(wheel, sums, digest)
        self.assertEqual(both["status"], "READY")

    def test_wheel_contents_must_match_its_own_record(self):
        wheel, sums = self.make_wheel("1.3.1", {"001": MIGRATION_A}, tamper=True)
        with self.assertRaisesRegex(up.PlanError, "RECORD"):
            self.plan(wheel, sums)

    def test_unsafe_paths_in_wheel_are_refused(self):
        wheel, _ = self.make_wheel("1.3.1", {"001": MIGRATION_A})
        with zipfile.ZipFile(wheel, "a") as z:
            z.writestr("../escape.py", b"x")
        sums = self.root / "SHA256SUMS"
        sums.write_text("%s  %s\n" % (hashlib.sha256(wheel.read_bytes()).hexdigest(), wheel.name))
        with self.assertRaisesRegex(up.PlanError, "unsafe path"):
            self.plan(wheel, sums)

    def test_command_is_registered(self):
        args = cli._build_parser().parse_args(["upgrade-plan", "--wheel", "x.whl", "--sha256", "ab"])
        self.assertEqual((args.cmd, args.wheel), ("upgrade-plan", "x.whl"))
        self.assertEqual(cli.COMMANDS["upgrade-plan"].__name__, "_cmd_upgrade_plan")


if __name__ == "__main__":
    unittest.main()
