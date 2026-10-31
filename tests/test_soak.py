"""The soak kit: checks, hash-chained driver and the real fixture cycles (no systemd, no network)."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "qualification" / "soak"
sys.path.insert(0, str(KIT))
sys.dont_write_bytecode = True

import checks  # noqa: E402
import common  # noqa: E402
import driver  # noqa: E402
import fixture_cycles  # noqa: E402
import launch  # noqa: E402
import sample  # noqa: E402

BOOT = Path("/proc/sys/kernel/random/boot_id").read_text().strip()


class CommonTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def test_save_never_overwrites_and_is_private(self):
        path = self.dir / "a.json"
        common.save(path, {"a": 1})
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
        with self.assertRaises(FileExistsError):
            common.save(path, {"a": 2})
        self.assertEqual(common.load(path), {"a": 1})

    def test_load_rejects_duplicate_keys_links_and_hard_links(self):
        dup = self.dir / "dup.json"
        dup.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            common.load(dup)
        target = self.dir / "t.json"
        common.save(target, {})
        link = self.dir / "link.json"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            common.read_bytes(link)
        os.link(target, self.dir / "hard.json")
        with self.assertRaisesRegex(ValueError, "hard-linked"):
            common.read_bytes(target)

    def test_interval_requires_both_clocks_to_agree(self):
        a = {"utc_ns": 10**18, "monotonic_ns": 10**12}
        common.check_interval(a, {"utc_ns": 10**18 + 5 * 10**9, "monotonic_ns": 10**12 + 5 * 10**9}, 420)
        with self.assertRaisesRegex(ValueError, "discontinuity"):
            common.check_interval(a, {"utc_ns": 10**18 + 60 * 10**9, "monotonic_ns": 10**12 + 5 * 10**9})
        with self.assertRaisesRegex(ValueError, "gap exceeded"):
            common.check_interval(a, {"utc_ns": 10**18 + 500 * 10**9, "monotonic_ns": 10**12 + 500 * 10**9}, 420)


class InstallChecksTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def package(self):
        package = self.dir / "rackmarshal"
        (package / "sub").mkdir(parents=True)
        (package / "a.py").write_text("a")
        (package / "sub" / "b.py").write_text("b")
        (package / "__pycache__").mkdir()
        (package / "__pycache__" / "a.pyc").write_bytes(b"x")
        return package

    def test_installed_files_detects_change_extra_and_missing(self):
        package = self.package()
        pinned = checks.hash_package(package)
        self.assertEqual(checks.installed_files(package, pinned)["files"], 2)
        (package / "a.py").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            checks.installed_files(package, pinned)
        (package / "a.py").write_text("a")
        (package / "extra.py").write_text("x")
        with self.assertRaisesRegex(ValueError, "extra"):
            checks.installed_files(package, pinned)
        (package / "extra.py").unlink()
        (package / "sub" / "b.py").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            checks.installed_files(package, pinned)

    def test_installed_package_may_not_contain_links(self):
        package = self.package()
        (package / "l.py").symlink_to(package / "a.py")
        with self.assertRaisesRegex(ValueError, "link"):
            checks.hash_package(package)

    def runner(self, states, failed="", restarts="0"):
        def run(argv, timeout=15):
            if "--failed" in argv:
                return 0, failed
            unit = argv[2]
            return 0, "ActiveState=%s\nNRestarts=%s\n" % (states.get(unit, "active"), restarts)
        return run

    def test_units_pass_and_each_failure_mode_fails(self):
        self.assertEqual(checks.units(self.runner({}))["result"], "PASS")
        with self.assertRaisesRegex(ValueError, "notify.timer is not active"):
            checks.units(self.runner({"rackmarshal-notify.timer": "inactive"}))
        with self.assertRaisesRegex(ValueError, "failed units"):
            checks.units(self.runner({}, failed="rackmarshal-domain@zfs.service loaded failed failed x"))
        with self.assertRaisesRegex(ValueError, "restarted"):
            checks.units(self.runner({}, restarts="2"))

    def test_status_api(self):
        def good(path):
            return 200, {"api_version": "v1"}
        self.assertEqual(checks.status_api(good)["result"], "PASS")
        with self.assertRaisesRegex(ValueError, "returned 500"):
            checks.status_api(lambda path: (500, {}))
        with self.assertRaisesRegex(ValueError, "API version"):
            checks.status_api(lambda path: (200, {"api_version": "v2"}))

    def make_db(self, path, ids=("001", "002")):
        with closing(sqlite3.connect(path)) as c:
            c.execute("CREATE TABLE schema_migrations(id TEXT)")
            c.executemany("INSERT INTO schema_migrations VALUES(?)", [(i,) for i in ids])
            c.commit()

    def test_database_checks_migrations_and_integrity(self):
        db = self.dir / "state.db"
        self.make_db(db)
        self.assertEqual(checks.database(db, ["001", "002"])["migrations"], 2)
        with self.assertRaisesRegex(ValueError, "migrations differ"):
            checks.database(db, ["001"])

    def test_snapshots_need_a_recent_valid_file_and_latest(self):
        snaps = self.dir / "snaps"
        snaps.mkdir()
        with self.assertRaisesRegex(ValueError, "no database snapshot"):
            checks.snapshots(snaps)
        newest = snaps / "state.db.20260101-031500Z"
        self.make_db(newest)
        with self.assertRaisesRegex(ValueError, "latest is missing"):
            checks.snapshots(snaps)
        self.make_db(snaps / "state.db.latest")
        self.assertEqual(checks.snapshots(snaps)["snapshots"], 1)
        with self.assertRaisesRegex(ValueError, "old"):
            checks.snapshots(snaps, now=time.time() + 27 * 3600)
        newest.write_bytes(b"not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            checks.snapshots(snaps)

    def test_snapshot_retention_must_be_applied(self):
        snaps = self.dir / "snaps"
        snaps.mkdir()
        self.make_db(snaps / "state.db.latest")
        for day in range(1, 10):
            self.make_db(snaps / ("state.db.202601%02d-031500Z" % day))
        with self.assertRaisesRegex(ValueError, "retention not applied"):
            checks.snapshots(snaps)

    def test_journal_errors_fail_on_any_line(self):
        self.assertEqual(checks.journal_errors("x", lambda argv, timeout=15: (0, "\n"))["result"], "PASS")
        with self.assertRaisesRegex(ValueError, "error log lines"):
            checks.journal_errors("x", lambda argv, timeout=15: (0, "Traceback boom\n"))
        with self.assertRaisesRegex(ValueError, "journalctl failed"):
            checks.journal_errors("x", lambda argv, timeout=15: (1, ""))

    def test_resources_records_free_space_and_service_memory(self):
        result = checks.resources(self.dir, lambda argv, timeout=15: (0, "MainPID=5\nMemoryCurrent=1000\n"))
        self.assertEqual(result["status_service"]["MemoryCurrent"], "1000")


class FixtureCyclesTests(unittest.TestCase):
    def test_nine_cycles_pass_against_this_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = fixture_cycles.run_cycles(sys.executable, ROOT, directory)
            self.assertEqual((receipt["result"], receipt["cycle_count"], receipt["invalid_ingestion_cases"]),
                             ("FIXTURE_ASSERTIONS_PASS", 9, 7))
            self.assertEqual(receipt["parser"], {"parser_cases": 15})

    def test_the_fixture_child_cannot_write_outside_its_directory_or_use_the_network(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            probe = Path(directory) / "outside.txt"
            for code in ("open(%r,'w').write('x')" % str(probe),
                         "import socket;socket.socket().connect(('127.0.0.1',9))",
                         "import subprocess;subprocess.run(['true'])"):
                import subprocess
                done = subprocess.run([sys.executable, "-I", "-B", "-S", "-c",
                                       fixture_cycles.CHILD.replace('module = sys.argv[3]', 'module = "x"') + "\n" + code,
                                       str(work), str(ROOT), "x"], capture_output=True, text=True)
                self.assertNotEqual(done.returncode, 0, code)
            self.assertFalse(probe.exists())


def kit_hashes():
    return {p.name: common.sha256(p.read_bytes()) for p in sorted(KIT.glob("*.py"))}


class DriverTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        for name in ("samples", "receipts"):
            (self.work / name).mkdir()
        self.config = {"source_commit": "c" * 40, "boot_id": BOOT, "kit_hashes": kit_hashes(),
                       "launched_utc_ns": time.time_ns()}
        common.save(self.work / "config.json", self.config)
        self.failures = 0

    def fake_sampler(self, fail_first=0, result="CHECKS_PASS"):
        """A stand-in for sample.py that writes the same files without running any check."""
        state = {"left": fail_first}

        def run_once(out):
            (out / "sampler.log").write_text("log\n")
            if state["left"] > 0:
                state["left"] -= 1
                (out / "checks").mkdir()
                return 1
            (out / "checks").mkdir()
            summary = {}
            for name in driver.CHECKS:
                common.save(out / "checks" / (name + ".json"), {"result": "PASS"})
                digest = common.sha256((out / "checks" / (name + ".json")).read_bytes())
                summary[name] = {"result": "PASS", "execution_receipt": name + ".json",
                                 "execution_receipt_sha256": digest}
            common.save(out / "checks" / "SAMPLE.json", {"result": result, "checks": summary})
            return 0
        return run_once

    def take(self, **kwargs):
        time.sleep(0.01)
        return driver.take_sample(self.work, KIT, self.fake_sampler(**kwargs))

    def test_samples_chain_and_validate(self):
        first = self.take()
        second = self.take()
        self.assertEqual((first["index"], second["index"]), (0, 1))
        rows, head = driver.validate_chain(self.work, self.config)
        self.assertEqual(len(rows), 2)
        self.assertEqual(second["previous_sha256"], common.sha256(common.canonical(first)))
        self.assertTrue((self.work / "START.json").is_file())

    def test_check_lists_agree_across_modules(self):
        self.assertEqual(driver.CHECKS, sample.CHECKS)

    def test_edited_evidence_edited_receipt_and_missing_receipt_are_detected(self):
        self.take()
        self.take()
        evidence = next((self.work / "samples" / "00000000" / "checks").glob("units.json"))
        original = evidence.read_bytes()
        evidence.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            driver.validate_chain(self.work, self.config)
        evidence.write_bytes(original)
        driver.validate_chain(self.work, self.config)
        (self.work / "receipts" / "00000000.json").rename(self.work / "receipts" / "00000005.json")
        with self.assertRaisesRegex(ValueError, "receipt gap"):
            driver.validate_chain(self.work, self.config)

    def test_rewriting_an_earlier_receipt_is_detected_even_in_canonical_form(self):
        self.take()
        self.take()
        path = self.work / "receipts" / "00000000.json"
        row = common.load(path)
        row["scope"] = "edited afterwards"
        path.unlink()
        common.save(path, row)
        with self.assertRaisesRegex(ValueError, "receipt chain|start record|intent differs"):
            driver.validate_chain(self.work, self.config)

    def test_extra_file_in_a_sample_is_detected(self):
        self.take()
        (self.work / "samples" / "00000000" / "planted.txt").write_text("x")
        with self.assertRaisesRegex(ValueError, "unlisted sample evidence"):
            driver.validate_chain(self.work, self.config)

    def test_one_failure_is_quarantined_and_retried(self):
        row = self.take(fail_first=1)
        self.assertEqual(row["attempts"], 2)
        glitch = self.work / "glitches" / "00000000-attempt1"
        self.assertTrue((glitch / "GLITCH.json").is_file() and (glitch / "sampler.log").is_file())
        self.assertEqual(len(driver.validate_chain(self.work, self.config)[0]), 1)

    def test_second_failure_of_one_sample_stops(self):
        with self.assertRaisesRegex(ValueError, "failed twice"):
            self.take(fail_first=2)

    def test_third_glitch_in_a_window_exhausts_the_budget(self):
        self.take(fail_first=1)
        self.take(fail_first=1)
        with self.assertRaisesRegex(ValueError, "glitch budget exhausted"):
            self.take(fail_first=1)

    def test_a_glitch_record_without_a_retried_sample_is_rejected(self):
        self.take()
        (self.work / "glitches").mkdir()
        (self.work / "glitches" / "00000000-attempt1").mkdir()
        (self.work / "glitches" / "00000000-attempt1" / "GLITCH.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "do not match"):
            driver.validate_chain(self.work, self.config)

    def test_failed_sample_result_never_becomes_a_receipt(self):
        with self.assertRaisesRegex(ValueError, "sample result"):
            self.take(result="FAIL")
        self.assertEqual(list((self.work / "receipts").iterdir()), [])

    def test_stop_and_complete_markers_refuse_further_samples(self):
        for marker in ("STOP.json", "COMPLETE.json"):
            common.save(self.work / marker, {})
            with self.assertRaisesRegex(ValueError, "stopped or completed"):
                self.take()
            (self.work / marker).unlink()

    def test_changed_kit_file_is_refused(self):
        self.config["kit_hashes"]["driver.py"] = "0" * 64
        (self.work / "config.json").unlink()
        common.save(self.work / "config.json", self.config)
        with self.assertRaisesRegex(ValueError, "kit file changed: driver.py"):
            self.take()

    def test_other_boot_is_refused(self):
        self.config["boot_id"] = "not-this-boot"
        (self.work / "config.json").unlink()
        common.save(self.work / "config.json", self.config)
        with self.assertRaisesRegex(ValueError, "boot changed"):
            self.take()

    def short_window(self, seconds, minimum):
        driver.WINDOW_NS, driver.MIN_SAMPLES = int(seconds * 10**9), minimum
        self.addCleanup(setattr, driver, "WINDOW_NS", 86400 * 10**9)
        self.addCleanup(setattr, driver, "MIN_SAMPLES", 280)

    def test_a_long_enough_window_with_too_few_samples_does_not_complete(self):
        self.short_window(0.4, 4)
        self.take()
        self.take()
        time.sleep(0.45)
        with self.assertRaisesRegex(ValueError, "too few samples"):
            self.take()
        self.assertFalse((self.work / "COMPLETE.json").exists())

    def test_window_completion_writes_a_summary(self):
        self.short_window(0.4, 3)
        self.take()
        self.take()
        self.assertFalse((self.work / "COMPLETE.json").exists())
        time.sleep(0.45)
        self.take()
        done = common.load(self.work / "COMPLETE.json")
        self.assertEqual((done["result"], done["samples"]), ("SOAK_WINDOW_COMPLETE", 3))

    def test_journal_window_starts_at_the_previous_sample(self):
        self.assertEqual(driver.journal_since(0), "1970-01-01 00:00:00 UTC")


class LauncherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def test_invocation_problems_name_each_wrong_flag(self):
        good = dict(isolated=1, no_bytecode=True, umask=0o077, euid=0, platform="linux", version=(3, 11))
        self.assertEqual(launch.invocation_problems(**good), [])
        for key, bad, text in (("isolated", 0, "-I"), ("no_bytecode", False, "-B"), ("umask", 0o022, "umask 077"),
                               ("euid", 1000, "root"), ("platform", "darwin", "Linux"), ("version", (3, 10), "3.11")):
            problems = launch.invocation_problems(**dict(good, **{key: bad}))
            self.assertEqual(len(problems), 1, key)
            self.assertIn(text, problems[0])

    def test_target_needs_matching_hostname_and_a_deliberate_marker(self):
        marker = self.dir / "marker"
        uid = os.getuid()
        self.assertIn("missing", launch.target_problems("box", "box", marker, uid)[0])
        marker.write_text("other\n")
        marker.chmod(0o644)
        self.assertIn("does not contain", launch.target_problems("box", "box", marker, uid)[0])
        marker.write_text("box\n")
        self.assertEqual(launch.target_problems("box", "box", marker, uid), [])
        self.assertIn("does not match", launch.target_problems("box2", "box", marker, uid)[0])
        marker.chmod(0o666)
        self.assertIn("cannot write", launch.target_problems("box", "box", marker, uid)[0])
        marker.chmod(0o644)
        self.assertIn("root-owned", launch.target_problems("box", "box", marker, uid + 1)[0])
        marker.unlink()
        marker.symlink_to(self.dir)
        self.assertTrue(launch.target_problems("box", "box", marker, uid))

    def test_the_real_kit_is_complete_and_extra_files_are_refused(self):
        self.assertEqual(launch.kit_problems(KIT), [])
        copy = self.dir / "kit"
        copy.mkdir()
        for name in launch.KIT_FILES + ("launch.py",):
            (copy / name).write_text("x")
        self.assertEqual(launch.kit_problems(copy), [])
        (copy / "extra.py").write_text("x")
        self.assertIn("differ", launch.kit_problems(copy)[0])
        (copy / "extra.py").unlink()
        (copy / "__pycache__").mkdir()
        self.assertIn("__pycache__", " ".join(launch.kit_problems(copy)))

    def test_source_commit_existing_paths_and_space(self):
        self.assertEqual(launch.source_commit_problems("a" * 40), [])
        for bad in ("a" * 39, "A" * 40, "g" * 40, ""):
            self.assertTrue(launch.source_commit_problems(bad))
        self.assertTrue(launch.existing_problems([self.dir]))
        self.assertEqual(launch.existing_problems([self.dir / "nope"]), [])
        self.assertTrue(launch.space_problems(self.dir, 2**62))
        self.assertEqual(launch.space_problems(self.dir, 1), [])

    def test_unit_text_is_hardened_and_never_enabled_at_boot(self):
        service, timer = launch.unit_texts("/w", "/k", 42)
        for required in ("ConditionPathExists=!/w/STOP.json", "ConditionPathExists=!/w/COMPLETE.json",
                         "User=rackmarshal", "Group=42", "NoNewPrivileges=yes", "ProtectSystem=strict",
                         "ReadWritePaths=/w", "IPAddressDeny=any", "IPAddressAllow=localhost", "TimeoutStartSec=290",
                         "ExecStart=/usr/bin/python3 -I -B -S /k/driver.py /w", "ExecStopPost=", "KillMode=control-group"):
            self.assertIn(required, service)
        self.assertNotIn("[Install]", service + timer)
        self.assertIn("Persistent=false", timer)

    def test_copy_kit_pins_read_only_copies_and_never_overwrites(self):
        destination = self.dir / "dest"
        hashes = launch.copy_kit(KIT, destination)
        self.assertEqual(set(hashes), set(launch.KIT_FILES))
        for name, digest in hashes.items():
            self.assertEqual(common.sha256((destination / name).read_bytes()), digest)
            self.assertEqual((destination / name).stat().st_mode & 0o777, 0o444)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o555)
        with self.assertRaises(FileExistsError):
            launch.copy_kit(KIT, destination)

    # -- full launch with a fake machine ---------------------------------------------------------
    def machine(self):
        venv = self.dir / "venv"
        package = venv / "lib" / "python3.13" / "site-packages" / "rackmarshal"
        (package / "db" / "migrations").mkdir(parents=True)
        (package / "a.py").write_text("a")
        (package / "db" / "migrations" / "001_x.sql").write_text("-- x")
        (package / "db" / "migrations" / "002_y.sql").write_text("-- y")
        state = self.dir / "state"
        state.mkdir()
        (state / "db-snapshots").mkdir()
        with closing(sqlite3.connect(state / "state.db")) as c:
            c.execute("CREATE TABLE schema_migrations(id TEXT)")
            c.executemany("INSERT INTO schema_migrations VALUES(?)", [("001",), ("002",)])
            c.commit()
        (self.dir / "units").mkdir()
        (self.dir / "launch").mkdir()
        return dict(kit=KIT, source_commit="d" * 40, hostname="box", venv=venv, state_db=state / "state.db",
                    snapshot_dir=state / "db-snapshots", kit_dest=self.dir / "kit-dest", work=self.dir / "work",
                    unit_dir=self.dir / "units", launch_dir=self.dir / "launch",
                    owner=(os.getuid(), os.getgid()), boot_id=BOOT)

    def fake_systemctl(self, args, first_sample_ok=True):
        calls = []

        def run(argv, timeout=60):
            calls.append(argv[1:])
            if argv[1:3] == ["start", "rmq-soak.service"]:
                if not first_sample_ok:
                    return 1, ""
                helper = DriverTests("test_samples_chain_and_validate")
                helper.work = args["work"]
                helper.failures = 0
                driver.take_sample(args["work"], args["kit_dest"], helper.fake_sampler())
                return 0, ""
            if argv[1] == "is-active":
                return 0, "active\n"
            if argv[0].endswith("python"):
                return 0, "1.3.0rc1\n"
            return 0, ""
        run.calls = calls
        return run

    def test_launch_takes_the_first_sample_before_starting_the_timer(self):
        args = self.machine()
        run = self.fake_systemctl(args)
        report = launch.launch(run=run, **args)
        self.assertEqual((report["result"], report["enabled_on_boot"], report["completion"]),
                         ("SOAK_STARTED", False, "PENDING"))
        order = [c for c in run.calls if c[0] in ("start", "daemon-reload")]
        self.assertEqual(order, [["daemon-reload"], ["start", "rmq-soak.service"], ["start", "rmq-soak.timer"]])
        config = common.load(args["work"] / "config.json")
        self.assertEqual((config["package_version"], config["migrations"], config["source_commit"]),
                         ("1.3.0rc1", ["001", "002"], "d" * 40))
        self.assertEqual(set(config["package_hashes"]), {"a.py", "db/migrations/001_x.sql", "db/migrations/002_y.sql"})
        self.assertEqual((args["work"] / "config.json").stat().st_mode & 0o777, 0o400)
        self.assertTrue((args["launch_dir"] / "LAUNCHED.json").is_file())
        self.assertTrue((args["unit_dir"] / "rmq-soak.timer").is_file())
        self.assertEqual(len(driver.validate_chain(args["work"], config)[0]), 1)

    def test_a_failed_first_sample_stops_everything_and_never_starts_the_timer(self):
        args = self.machine()
        run = self.fake_systemctl(args, first_sample_ok=False)
        with self.assertRaisesRegex(ValueError, "first sample failed"):
            launch.launch(run=run, **args)
        self.assertNotIn(["start", "rmq-soak.timer"], run.calls)
        self.assertIn(["stop", "rmq-soak.service"], run.calls)
        self.assertTrue((args["work"] / "STOP.json").is_file())
        self.assertFalse((args["launch_dir"] / "LAUNCHED.json").exists())

    def test_a_corrupt_first_sample_is_caught_before_the_timer_starts(self):
        args = self.machine()
        inner = self.fake_systemctl(args)

        def run(argv, timeout=60):
            result = inner(argv, timeout)
            if argv[1:3] == ["start", "rmq-soak.service"]:
                evidence = next((args["work"] / "samples" / "00000000" / "checks").glob("units.json"))
                evidence.write_bytes(evidence.read_bytes() + b" ")
            return result
        run.calls = inner.calls
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            launch.launch(run=run, **args)
        self.assertNotIn(["start", "rmq-soak.timer"], inner.calls)
        self.assertTrue((args["work"] / "STOP.json").is_file())

    def test_a_timer_that_will_not_start_stops_the_launch(self):
        args = self.machine()
        inner = self.fake_systemctl(args)

        def run(argv, timeout=60):
            if argv[1:3] == ["start", "rmq-soak.timer"]:
                inner.calls.append(argv[1:])
                return 1, ""
            return inner(argv, timeout)
        run.calls = inner.calls
        with self.assertRaisesRegex(ValueError, "timer did not start"):
            launch.launch(run=run, **args)
        self.assertTrue((args["work"] / "STOP.json").is_file())
        self.assertFalse((args["launch_dir"] / "LAUNCHED.json").exists())

    def test_unreadable_paths_are_reported_not_crashed_on(self):
        problems = launch.existing_problems(["/proc/1/root/definitely/not/readable/by/a/normal/user"])
        self.assertTrue(problems == [] or "cannot inspect" in problems[0])

    def test_a_launch_is_never_repeated(self):
        args = self.machine()
        launch.launch(run=self.fake_systemctl(args), **args)
        self.assertTrue(launch.existing_problems([args["kit_dest"], args["work"],
                                                  args["launch_dir"] / "LAUNCH-INTENT.json"]))
        with self.assertRaises(FileExistsError):
            launch.launch(run=self.fake_systemctl(args), **args)

    def test_migration_count_must_match_the_installed_files(self):
        args = self.machine()
        (args["venv"] / "lib" / "python3.13" / "site-packages" / "rackmarshal" / "db" / "migrations" / "003_z.sql").write_text("-- z")
        with self.assertRaisesRegex(ValueError, "migrations"):
            launch.build_config(source_commit="d" * 40, venv=args["venv"], state_db=args["state_db"],
                                snapshot_dir=args["snapshot_dir"], kit_hashes={}, boot_id=BOOT, hostname="box",
                                run=lambda argv, timeout=60: (0, "x"))

    def test_command_line_refuses_without_changing_anything(self):
        import subprocess
        done = subprocess.run([sys.executable, "-I", "-B", str(KIT / "launch.py"), "--target-hostname", "not-this-host",
                               "--source-commit", "nothex"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("PREFLIGHT_FAILED", done.stdout)
        self.assertIn("does not match this machine", done.stdout)
        self.assertIn("40 lowercase hex", done.stdout)


if __name__ == "__main__":
    unittest.main()
