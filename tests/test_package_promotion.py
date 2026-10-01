"""Exercise real code promotion in disposable installations; never systemd."""
import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "promote-package-files.py"
spec = importlib.util.spec_from_file_location("package_promotion", SCRIPT)
promotion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promotion)


class Runtime:
    def __init__(self):
        self.calls = []

    def snapshot(self):
        self.calls.append("snapshot")
        return []

    def quiesce(self, snapshot):
        self.calls.append("quiesce")

    def start_apps(self, snapshot):
        self.calls.append("ready")

    def resume(self, snapshot):
        self.calls.append("resume")


class PackagePromotion(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.relative = "api/v1.py"
        self.source = self.repo / "rackmarshal" / self.relative
        self.source.parent.mkdir(parents=True)
        self.source.write_text("VALUE = 'new'\n")
        for path in promotion.ASSETS.values():
            asset = self.repo / path
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_text("{}\n" if path.endswith(".json") else "# fixture acceptance runner\n")
        self.revision = "1" * 40
        self.bundle = self.root / "bundle"
        manifest = {"format": 1, "revision": self.revision, "files": {}, "assets": {}}
        for destination, source in [("files/" + self.relative, "rackmarshal/" + self.relative)] + list(promotion.ASSETS.items()):
            target = self.bundle / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.repo / source, target)
            group = "files" if destination.startswith("files/") else "assets"
            key = self.relative if group == "files" else destination
            manifest[group][key] = promotion.digest(target)
        promotion.write_json(self.bundle / "manifest.json", manifest)
        self.roots = {name: self.root / name for name in ("status", "mcp")}
        for root in self.roots.values():
            target = root / self.relative
            target.parent.mkdir(parents=True)
            target.write_text("VALUE = 'old'\n")
            target.chmod(0o640)
        self.backups = self.root / "backups"
        self.runtime = Runtime()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

    def apply(self, acceptance=lambda transaction: None):
        return promotion.promote(self.bundle, self.roots, self.backups, self.runtime, acceptance)

    def journal(self):
        path = next(self.backups.glob("*/transaction.json"))
        return path.parent, json.loads(path.read_text())

    @unittest.skipUnless(shutil.which("git"), "Git preparation runs on staging; target installation has no Git dependency")
    def test_committed_source_is_immutable_and_moving_ref_is_rejected(self):
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "Fixture")
        self.revision = self.git("rev-parse", "HEAD").strip()
        self.source.write_text("VALUE = 'uncommitted'\n")
        promotion.prepare(self.repo, self.revision, ["rackmarshal/" + self.relative], self.root / "second")
        self.assertEqual((self.root / "second/files" / self.relative).read_text(), "VALUE = 'new'\n")
        with self.assertRaises(ValueError):
            promotion.prepare(self.repo, "HEAD", ["rackmarshal/" + self.relative], self.root / "invalid")

    def test_two_installations_are_verified_before_acceptance_and_timers_resume_last(self):
        for root in self.roots.values():
            cache = root / "api/__pycache__"
            cache.mkdir()
            (cache / "v1.cpython-fixture.pyc").write_bytes(b"stale")
        def accept(transaction):
            self.runtime.calls.append("accept")
            for root in self.roots.values():
                self.assertEqual((root / self.relative).read_text(), "VALUE = 'new'\n")
                self.assertEqual((root / self.relative).stat().st_mode & 0o777, 0o640)
                self.assertFalse(list((root / "api/__pycache__").glob("*.pyc")))
        report = self.apply(accept)
        self.assertEqual(report["state"], "ACCEPTED")
        self.assertEqual(report["changed_files"], 2)
        self.assertEqual(self.runtime.calls, ["snapshot", "quiesce", "ready", "accept", "resume"])
        transaction, journal = self.journal()
        self.assertEqual(journal["revision"], self.revision)
        promotion.restore_files(transaction, journal)
        for root in self.roots.values():
            self.assertEqual((root / self.relative).read_text(), "VALUE = 'old'\n")

    def test_unchanged_sources_do_not_restart_services_or_create_backups(self):
        self.apply()
        self.runtime.calls.clear()
        report = self.apply(lambda _: self.fail("No-op must not run acceptance"))
        self.assertEqual(report["state"], "UNCHANGED")
        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(len(list(self.backups.iterdir())), 1)

    def test_acceptance_failure_restores_both_installations_and_runtime(self):
        def fail(transaction):
            raise RuntimeError("Fixture MCP acceptance failure")
        with self.assertRaisesRegex(RuntimeError, "ROLLED_BACK"):
            self.apply(fail)
        _, journal = self.journal()
        self.assertEqual(journal["state"], "ROLLED_BACK")
        self.assertEqual(self.runtime.calls[-3:], ["quiesce", "ready", "resume"])
        for root in self.roots.values():
            self.assertEqual((root / self.relative).read_text(), "VALUE = 'old'\n")

    def test_partial_copy_failure_restores_the_already_written_package(self):
        original = promotion.replace_file
        failed = False
        def copy(source, target, metadata=None):
            nonlocal failed
            if target == (self.roots["mcp"] / self.relative).resolve() and not failed:
                failed = True
                raise OSError("Fixture write failure")
            return original(source, target, metadata)
        with patch.object(promotion, "replace_file", side_effect=copy):
            with self.assertRaisesRegex(RuntimeError, "ROLLED_BACK"):
                self.apply()
        self.assertTrue(failed, "The intended partial-copy failure must be injected")
        for root in self.roots.values():
            self.assertEqual((root / self.relative).read_text(), "VALUE = 'old'\n")

    def test_readiness_failure_rolls_back_before_acceptance(self):
        calls = 0
        def ready(snapshot):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("Fixture readiness timeout")
        with patch.object(self.runtime, "start_apps", side_effect=ready):
            with self.assertRaisesRegex(RuntimeError, "ROLLED_BACK"):
                self.apply(lambda _: self.fail("Acceptance must wait for readiness"))
        self.assertEqual(calls, 2)
        for root in self.roots.values():
            self.assertEqual((root / self.relative).read_text(), "VALUE = 'old'\n")

    def test_systemd_stops_timer_targets_even_if_inactive_at_snapshot(self):
        runtime = promotion.SystemdRuntime([], 1, "http://127.0.0.1:8000/mcp")
        commands = []
        def command(*args):
            commands.append(args)
            if args[0] == "list-units":
                return "rackmarshal-status.service loaded active running\nrackmarshal-mcp.service loaded active running\nrackmarshal-domain@ha.timer loaded active waiting\nrackmarshal-tunnel.service loaded active running\n"
            if args[-1] == "--value":
                return "rackmarshal-domain@ha.service\n"
            if args[0] == "show":
                return ("ActiveState=inactive\nType=oneshot\n" if args[1] == "rackmarshal-domain@ha.service"
                        else "ActiveState=active\nType=simple\n")
            return ""
        with patch.object(runtime, "command", side_effect=command):
            snapshot = runtime.snapshot()
            runtime.quiesce(snapshot)
            runtime.resume(snapshot)
        stops = [item for item in commands if item[0] == "stop"]
        self.assertIn("rackmarshal-domain@ha.service", stops[1])
        self.assertEqual(stops[0], ("stop", "rackmarshal-domain@ha.timer"))
        starts = [item for item in commands if item[0] == "start"]
        self.assertEqual(starts, [("start", "rackmarshal-domain@ha.timer")])
        self.assertFalse(any("rackmarshal-tunnel.service" in item for item in stops))

    def test_tampered_bundle_is_rejected_before_runtime_or_file_changes(self):
        (self.bundle / "files" / self.relative).write_text("VALUE = 'tampered'\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.apply()
        self.assertEqual(self.runtime.calls, [])
        self.assertFalse(self.backups.exists())

    def test_failed_promotion_removes_a_file_absent_before_installation(self):
        (self.roots["mcp"] / self.relative).unlink()
        def fail(transaction):
            self.assertTrue((self.roots["mcp"] / self.relative).is_file())
            raise RuntimeError("Fixture failed acceptance")
        with self.assertRaisesRegex(RuntimeError, "ROLLED_BACK"):
            self.apply(fail)
        self.assertFalse((self.roots["mcp"] / self.relative).exists())
        self.assertEqual((self.roots["status"] / self.relative).read_text(), "VALUE = 'old'\n")

    def test_symlink_target_and_parent_escape_are_rejected(self):
        target = self.roots["status"] / self.relative
        target.unlink()
        target.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.apply()
        with self.assertRaises(ValueError):
            promotion.child(self.root, "../outside.py")
        with self.assertRaises(ValueError):
            promotion.code_path("rackmarshal/db/migrations/new.py")

    def test_recovery_refuses_to_overwrite_a_later_unrelated_change(self):
        def conflict(transaction):
            (self.roots["status"] / self.relative).write_text("VALUE = 'external'\n")
            raise RuntimeError("Fixture acceptance failure")
        with self.assertRaisesRegex(RuntimeError, "ROLLBACK_FAILED"):
            self.apply(conflict)
        self.assertEqual((self.roots["status"] / self.relative).read_text(), "VALUE = 'external'\n")
        self.assertNotIn("resume", self.runtime.calls)

    def test_only_loopback_acceptance_endpoints_are_allowed(self):
        self.assertEqual(promotion.local_url("http://127.0.0.1:9110/"), "http://127.0.0.1:9110")
        for url in ("https://example.invalid", "http://user:pass@localhost", "http://localhost?token=fixture"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                promotion.local_url(url)

    def test_readiness_waits_for_http_startup_and_accepts_mcp_method_response(self):
        class Handler(BaseHTTPRequestHandler):
            attempts = 0
            def do_GET(self):
                if self.path == "/mcp":
                    status = 405
                else:
                    Handler.attempts += 1
                    status = 503 if Handler.attempts == 1 else 200
                self.send_response(status)
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:" + str(server.server_port)
            promotion.wait_ready([base + "/health"], 3, base + "/mcp")
            self.assertEqual(Handler.attempts, 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
