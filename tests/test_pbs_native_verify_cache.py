"""Exercise the installed observer source using fictional task history/QGA."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path("packaging/observers/pbs-native-verify-cache")
CACHE = "/var/lib/rackmarshal/pbs-verification.json"

class PbsNativeVerifyCacheTests(unittest.TestCase):
    def run_cache(self, rows, wrapper_exit=0, host_exit=0):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cache.json"
            def guest(argv, **kwargs):
                # Run the actual embedded guest query against fictional history.
                with patch("subprocess.check_output", return_value=json.dumps(rows)) as query:
                    text = io.StringIO()
                    with redirect_stdout(text):
                        exec(argv[-1], {})
                    command = query.call_args.args[0]
                    self.assertEqual(command[command.index("--limit")+1], "1000")
                envelope = {"exitcode":wrapper_exit,"out-data":text.getvalue()}
                return subprocess.CompletedProcess(argv, host_exit, json.dumps(envelope), "fixture host error" if host_exit else "")
            def path(name):
                return output if str(name) == CACHE else Path(name)
            with patch.object(sys, "argv", [str(SOURCE), "--vmid", "900", "--datastore", "example-store", "--job", "example-weekly", "--output", CACHE]), patch("subprocess.run", side_effect=guest), patch("pathlib.Path", side_effect=path), patch("time.time", return_value=20000):
                exec(compile(SOURCE.read_text(), str(SOURCE), "exec"), {})
            return json.loads(output.read_text())

    def weekly(self, status="OK", end=10000):
        return {"worker_type":"verificationjob", "worker_id":"example-store:example-weekly", "status":status,"starttime":9000,"endtime":end}

    def test_weekly_job_after_first_hundred_tasks_is_observed(self):
        unrelated = [{"worker_type":"backup","worker_id":"fixture","status":"OK"} for _ in range(132)]
        result = self.run_cache(unrelated+[self.weekly()])
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["age_hours"], round(10000/3600,3))
        self.assertEqual(result["errors"], [])

    def test_snapshot_success_is_not_weekly_job_evidence(self):
        result = self.run_cache([dict(self.weekly(), worker_type="verify"), dict(self.weekly(),worker_id="other:example-weekly")])
        self.assertIsNone(result["status"])
        self.assertIn("weekly_verification_task_not_found",result["errors"])

    def test_failed_latest_job_does_not_borrow_older_success(self):
        result = self.run_cache([self.weekly("ERROR"), self.weekly("OK",end=5000)])
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["endtime"],10000)

    def test_running_job_does_not_borrow_completed_success(self):
        result = self.run_cache([self.weekly(None,end=None), self.weekly()])
        self.assertIsNone(result["status"])
        self.assertIsNone(result["age_hours"])

    def test_host_execution_error_never_reports_success(self):
        result = self.run_cache([self.weekly()],host_exit=1)
        self.assertIsNone(result["status"])
        self.assertTrue(result["errors"])

    def test_guest_execution_error_never_reports_success(self):
        result = self.run_cache([self.weekly()], wrapper_exit=7)
        self.assertIsNone(result["status"])
        self.assertIn("guest_rc=7", result["errors"])
