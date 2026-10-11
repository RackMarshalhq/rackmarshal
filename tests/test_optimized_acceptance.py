"""Acceptance and baseline invariants must survive optimized interpreters."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OptimizedAcceptanceTests(unittest.TestCase):
    def run_python(self, code, flags=(), optimize=None):
        env = dict(os.environ)
        env.pop("PYTHONOPTIMIZE", None)
        if optimize is not None:
            env["PYTHONOPTIMIZE"] = optimize
        return subprocess.run([sys.executable, *flags, "-c", code], cwd=ROOT,
                              env=env, text=True, capture_output=True, timeout=20)

    def test_live_checks_fail_before_network_under_optimization(self):
        calls = (
            "from rackmarshal.agent.live_eval import assert_case; assert_case('bad', [{'data': {'status': 'BAD', 'database_readable': False}}], ['health_ok'])",
            "import asyncio; from rackmarshal.agent.live_eval import run_suite; asyncio.run(run_suite('/missing-suite.json', 'https://must-not-contact.invalid'))",
        )
        for flags, env_opt in ((('-O',), None), (('-OO',), None), ((), '1')):
            for code in calls:
                with self.subTest(flags=flags, env=env_opt, code=code):
                    result = self.run_python(code, flags, env_opt)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("acceptance requires assertions", result.stderr)
                    self.assertNotIn("ModuleNotFoundError", result.stderr)
                    self.assertNotIn("FileNotFoundError", result.stderr)

    def test_normal_live_checks_still_reject_bad_health(self):
        result = self.run_python("from rackmarshal.agent.live_eval import assert_case; import json; print(json.dumps(assert_case('bad', [{'data': {'status': 'BAD', 'database_readable': False}}], ['health_ok'])))")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('health_ok:', result.stdout)

    def test_baseline_count_mismatch_rolls_back_even_optimized(self):
        code = r'''import sys, sqlite3
sys.path.insert(0, "tests")
from test_pve_baseline_adoption import PveBaselineAdoptionTests
case = PveBaselineAdoptionTests()
case.setUp()
try:
    with sqlite3.connect(case.db) as conn:
        conn.execute("CREATE TRIGGER ignore_second BEFORE INSERT ON resource_baseline WHEN NEW.resource_key='9002' BEGIN SELECT RAISE(IGNORE); END")
    try:
        case.call(apply=True)
    except RuntimeError as exc:
        if "row count changed unexpectedly" not in str(exc):
            raise
    else:
        raise RuntimeError("mismatched adoption was accepted")
    if case.count() != 1:
        raise RuntimeError("partial adoption escaped rollback")
    if list(case.root.glob("pve-baseline-*/receipt.json")):
        raise RuntimeError("failure produced applied receipt")
    print("ROLLBACK_CONFIRMED")
finally:
    case.doCleanups()
'''
        for flags in ((), ('-O',), ('-OO',)):
            with self.subTest(flags=flags):
                result = self.run_python(code, flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('ROLLBACK_CONFIRMED', result.stdout)
