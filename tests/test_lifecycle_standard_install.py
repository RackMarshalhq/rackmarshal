"""A standard install has two extra timers and root-run commands leave bytecode behind;
the upgrade engine must handle both without weakening its exact-file check."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from tests import test_lifecycle_systemd as fixture
from rackmarshal.maintenance.lifecycle import Refused
from rackmarshal.maintenance.lifecycle_systemd import PERIODIC

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lifecycle_script", ROOT / "scripts/lifecycle.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


setUpModule = fixture.setUpModule
tearDownModule = fixture.tearDownModule


class StandardInstallUnitTests(unittest.TestCase):
    def setUp(self):
        fixture.RuntimeTests.setUp(self)  # reuse the fake systemd, without re-running its tests
        for name in PERIODIC:
            self.states[name] = "active" if name.endswith(".timer") else "inactive"
        original = self.rt.runner

        def runner(args):
            out = original(args)
            if args[1] == "show" and args[2].endswith("db-snapshot.service") and "Type" in " ".join(args):
                out = out.replace("Type=simple", "Type=oneshot")
            return out
        self.rt.runner = runner

    def test_periodic_timers_are_paused_and_restarted(self):
        before = self.rt.snapshot()
        for name in PERIODIC:
            self.assertIn(name, before["units"])
        self.rt.guard(self.root / "tx", before)
        for name in PERIODIC:
            self.assertTrue((self.units / (name + ".d") / "99-lifecycle-maintenance.conf").exists())
        self.rt.quiesce(before)
        self.assertTrue(all(value == "inactive" for value in self.states.values()))
        self.rt.resume(self.root / "tx", before, lambda: None)
        self.assertEqual(self.states["rackmarshal-db-snapshot.timer"], "active")
        self.assertEqual(self.states["rackmarshal-observation-prune.timer"], "active")
        self.assertFalse((self.root / "marker").exists())

    def test_periodic_units_are_optional(self):
        # An install without them still works (the base fixture has none).
        for name in PERIODIC:
            del self.states[name]
        self.assertFalse(set(PERIODIC) & set(self.rt.snapshot()["units"]))

    def test_foreign_override_on_periodic_unit_refused(self):
        directory = self.units / "rackmarshal-db-snapshot.timer.d"
        directory.mkdir()
        (directory / "99-lifecycle-maintenance.conf").write_text("foreign")
        with self.assertRaises(Refused):
            self.rt.guard(self.root / "tx", self.rt.snapshot())

    def test_inflight_snapshot_job_refused(self):
        self.states["rackmarshal-db-snapshot.service"] = "active"
        with self.assertRaises(Refused):
            self.rt.snapshot()


class BytecodeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.target = Path(directory.name)
        self.site = self.target / "lib/python3.11/site-packages"
        (self.site / "rackmarshal/core/__pycache__").mkdir(parents=True)
        (self.site / "rackmarshal/core/config.py").write_text("x = 1\n")

    def test_bytecode_is_removed_and_source_kept(self):
        cache = self.site / "rackmarshal/core/__pycache__"
        (cache / "config.cpython-311.pyc").write_bytes(b"\0")
        C.clear_bytecode(self.target)
        self.assertFalse(cache.exists())
        self.assertTrue((self.site / "rackmarshal/core/config.py").exists())

    def test_unexpected_files_in_cache_folder_are_not_deleted(self):
        cache = self.site / "rackmarshal/core/__pycache__"
        (cache / "config.cpython-311.pyc").write_bytes(b"\0")
        (cache / "evil.py").write_text("print('x')\n")
        C.clear_bytecode(self.target)
        self.assertTrue((cache / "evil.py").exists())
        self.assertFalse((cache / "config.cpython-311.pyc").exists())

    def test_symlinked_cache_is_left_alone(self):
        outside = self.target / "outside"
        outside.mkdir()
        (outside / "keep.pyc").write_bytes(b"\0")
        cache = self.site / "rackmarshal/core/__pycache__"
        cache.rmdir()
        os.symlink(outside, cache)
        C.clear_bytecode(self.target)
        self.assertTrue((outside / "keep.pyc").exists())


class RecoveryScanTests(unittest.TestCase):
    """The automatic undo must find the failed transaction even if an earlier refused run left an empty folder."""

    class FakeEngineModule:
        @staticmethod
        def read(path, owner):
            return Path(path).read_text()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Path(directory.name)

    def make(self, name, phase=None):
        folder = self.store / name
        folder.mkdir()
        if phase:
            (folder / "transaction.json").write_text('{"phase": "%s"}' % phase)

    def test_empty_leftover_folder_is_skipped(self):
        self.make("transaction-aaaa")
        self.make("transaction-bbbb", "RECOVERY_REQUIRED")
        self.make("transaction-cccc", "COMMITTED")
        found = C.failed_transactions(self.store, self.FakeEngineModule)
        self.assertEqual([p.name for p in found], ["transaction-bbbb"])

    def test_no_failed_transaction_gives_empty_list(self):
        self.make("transaction-aaaa")
        self.make("transaction-cccc", "COMMITTED")
        self.assertEqual(C.failed_transactions(self.store, self.FakeEngineModule), [])


if __name__ == "__main__":
    unittest.main()
