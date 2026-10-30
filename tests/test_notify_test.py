import io, json, os, tempfile, unittest
from contextlib import redirect_stdout
from rackmarshal import cli
from rackmarshal.notifications import delivery
from rackmarshal.notifications.testsend import send_test, TEST_NOTIFICATION_ID


class NotifyTestTests(unittest.TestCase):
    def _conf(self, extra=""):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "rackmarshal.conf")
        with open(p, "w") as f:
            f.write("STATE_DB=/nonexistent/state.db\n" + extra)
        return p

    def test_pass_sends_one_labelled_message_and_hides_token(self):
        calls = []
        report, code = send_test(
            self._conf(),
            loader=lambda path: ("http://fixture.invalid", "SECRET-TOKEN"),
            sender=lambda *a: calls.append(a),
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], TEST_NOTIFICATION_ID)
        self.assertNotIn("SECRET-TOKEN", json.dumps(report))

    def test_missing_credentials_fail_with_hint(self):
        def loader(path):
            raise delivery.DeliveryError("unable to load Home Assistant credential")
        report, code = send_test(self._conf(), loader=loader, sender=lambda *a: None)
        self.assertEqual(code, 2)
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("QUICKSTART", report["hint"])

    def test_delivery_failure_exits_2_and_does_not_leak_token(self):
        def sender(*a):
            raise delivery.DeliveryError("Home Assistant HTTP 401: unauthorized")
        report, code = send_test(
            self._conf(),
            loader=lambda path: ("http://fixture.invalid", "SECRET-TOKEN"),
            sender=sender,
        )
        self.assertEqual(code, 2)
        self.assertIn("401", report["error"])
        self.assertNotIn("SECRET-TOKEN", json.dumps(report))

    def test_bad_config_path_fails_cleanly(self):
        report, code = send_test("/nonexistent/rackmarshal.conf")
        self.assertEqual(code, 2)
        self.assertEqual(report["result"], "FAIL")

    def test_cli_wires_the_command(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["notify-test", "--config", "/nonexistent/rackmarshal.conf"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["result"], "FAIL")


if __name__ == "__main__":
    unittest.main()
