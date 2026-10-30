"""Pin the command-line behaviour: exact output and exit codes for many configurations.

Expected results live in cli_golden.json. They were generated from the code before
cli.py was rewritten for readability, so a refactor that changes any output fails here.
To regenerate after an intentional behaviour change: RM_UPDATE_GOLDEN=1 python -m unittest tests.test_cli_characterization
"""
import contextlib
import io
import json
import os
import re
import stat
import tempfile
import unittest
from pathlib import Path

from rackmarshal import cli

GOLDEN = Path(__file__).with_name("cli_golden.json")


def _write(path, text, mode=None):
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def build_cases(tmp):
    """Return {case_name: config_path}. All paths are inside tmp."""
    cases = {}

    def conf(name, text):
        p = tmp / f"{name}.conf"
        _write(p, text)
        cases[name] = str(p)

    cases["missing_file"] = str(tmp / "does-not-exist.conf")
    conf("base_only", "STATE_DB=%s/state.db\n" % tmp)
    conf("no_state_db", "SITE_NAME=x\n")
    conf("blank_domains", "STATE_DB=%s/state.db\nENABLED_DOMAINS=  ,  \n" % tmp)
    conf("unknown_domain", "STATE_DB=%s/state.db\nENABLED_DOMAINS=pve, Foo ,BAR\n" % tmp)
    conf("all_domains_bare", "STATE_DB=%s/state.db\nENABLED_DOMAINS=pve,zfs,backup,ha,hardware,mount\n" % tmp)
    conf(
        "hardware_serials_incomplete",
        "STATE_DB=%s/state.db\nENABLED_DOMAINS=hardware\nSITE_NAME=x\n"
        "HARDWARE_SSH_HOST=h\nHARDWARE_SSH_USER=u\nHARDWARE_SSH_KEY=k\nHARDWARE_KNOWN_HOSTS=kh\n"
        "HARDWARE_NVME_SERIALS=AAA, BBB\nHARDWARE_NVME_AAA_MODEL=m\n"
        "HARDWARE_HOT_THRESHOLD_C=60\nHARDWARE_HOT_REQUIRED_SAMPLES=2\nHARDWARE_URGENT_THRESHOLD_C=75\n"
        "HARDWARE_RECOVERY_THRESHOLD_C=55\nHARDWARE_RECOVERY_REQUIRED_SAMPLES=2\n" % tmp,
    )
    key_broad = tmp / "zfs_key_broad"
    hosts_ok = tmp / "known_hosts_ok"
    key_ok = tmp / "zfs_key_ok"
    _write(key_broad, "k", 0o644)
    _write(key_ok, "k", 0o600)
    _write(hosts_ok, "h", 0o600)
    zfs = "STATE_DB=%s/state.db\nENABLED_DOMAINS=zfs\nSITE_NAME=x\nZFS_SSH_HOST=h\nZFS_SSH_USER=u\n" % tmp
    conf("zfs_key_too_broad", zfs + f"ZFS_SSH_KEY={key_broad}\nZFS_KNOWN_HOSTS={hosts_ok}\n")
    # Both a missing setting and a too-open key file, plus an unknown domain and a hardware gap,
    # so the order in which problems are reported is pinned too.
    conf(
        "several_problems_at_once",
        "ENABLED_DOMAINS=zfs,hardware,nope\nSITE_NAME=x\nZFS_SSH_HOST=h\n"
        f"ZFS_SSH_KEY={key_broad}\nZFS_KNOWN_HOSTS={hosts_ok}\n"
        "HARDWARE_NVME_SERIALS=ZZZ\n",
    )
    conf("zfs_valid", zfs + f"ZFS_SSH_KEY={key_ok}\nZFS_KNOWN_HOSTS={hosts_ok}\n")
    conf("ha_missing_credential", "STATE_DB=%s/state.db\nENABLED_DOMAINS=ha\n" % tmp)
    return cases


def run(argv, tmp):
    out, err = io.StringIO(), io.StringIO()
    code = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = exc.code
        except Exception as exc:  # unexpected failures are part of the recorded behaviour
            code = f"EXC {type(exc).__name__}"

    def norm(text):
        text = text.replace(str(tmp), "<TMP>")
        return re.sub(r"(\d+\.\d+\.\d+)[0-9a-z.+-]*", "<VER>", text) if "version" in " ".join(argv) else text

    return {"argv": [norm(a) for a in argv], "code": code, "stdout": norm(out.getvalue()), "stderr": norm(err.getvalue())}


def collect():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d).resolve()
        results = []
        old_port = os.environ.pop("RACKMARSHAL_CONFIG", None)
        try:
            for name, path in sorted(build_cases(tmp).items()):
                for cmd in ("validate-config", "setup-plan", "diagnostic"):
                    r = run([cmd, "--config", path], tmp)
                    r["case"] = name
                    results.append(r)
            results.append(dict(run(["domains"], tmp), case="-"))
            results.append(dict(run(["--version"], tmp), case="-"))
            results.append(dict(run([], tmp), case="-"))
            results.append(dict(run(["no-such-command"], tmp), case="-"))
            results.append(dict(run(["validate-config", "--bogus"], tmp), case="-"))
        finally:
            if old_port is not None:
                os.environ["RACKMARSHAL_CONFIG"] = old_port
    return results


class CliCharacterizationTests(unittest.TestCase):
    def test_outputs_and_exit_codes_unchanged(self):
        results = collect()
        if os.environ.get("RM_UPDATE_GOLDEN") == "1":
            GOLDEN.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            self.skipTest("golden file regenerated")
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(len(results), len(expected))
        for got, want in zip(results, expected):
            with self.subTest(case=want["case"], argv=want["argv"]):
                self.assertEqual(got, want)


class CliDispatchTests(unittest.TestCase):
    """The two subcommands that touch the database or the network, checked with stand-ins."""

    def test_migrate_plan_and_apply_pass_arguments_and_restore_argv(self):
        import sys
        from unittest import mock

        seen = []

        def fake_migration_main():
            seen.append((list(sys.argv), os.environ.get("RACKMARSHAL_CONFIG")))
            return None

        saved_argv, saved_env = list(sys.argv), os.environ.get("RACKMARSHAL_CONFIG")
        try:
            with mock.patch("rackmarshal.db.migrations.migrate.main", fake_migration_main):
                self.assertEqual(cli.main(["migrate", "--config", "/x/a.conf"]), 0)
                self.assertEqual(cli.main(["migrate", "--config", "/x/b.conf", "--apply"]), 0)
            self.assertEqual(sys.argv, saved_argv)
        finally:
            if saved_env is None:
                os.environ.pop("RACKMARSHAL_CONFIG", None)
            else:
                os.environ["RACKMARSHAL_CONFIG"] = saved_env
        self.assertEqual(seen[0], (["rackmarshal-migrate", "--plan"], "/x/a.conf"))
        self.assertEqual(seen[1], (["rackmarshal-migrate", "--apply", "--yes"], "/x/b.conf"))

    def test_migrate_returns_the_tools_exit_code(self):
        from unittest import mock

        with mock.patch("rackmarshal.db.migrations.migrate.main", lambda: 7):
            self.assertEqual(cli.main(["migrate", "--config", "/x/c.conf"]), 7)
        os.environ.pop("RACKMARSHAL_CONFIG", None)

    def test_investigator_check_exit_codes_and_default_url(self):
        from unittest import mock

        urls = []

        def fake_check(url):
            urls.append(url)
            return {"result": "PASS" if len(urls) == 1 else "FAIL"}

        out = io.StringIO()
        with mock.patch("rackmarshal.mcp.check.connection_check", fake_check), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["investigator-check"]), 0)
            self.assertEqual(cli.main(["investigator-check", "--url", "http://h:1/mcp"]), 2)
        self.assertEqual(urls, ["http://127.0.0.1:8000/mcp", "http://h:1/mcp"])


if __name__ == "__main__":
    unittest.main()
