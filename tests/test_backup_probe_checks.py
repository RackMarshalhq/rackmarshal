import atexit
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_td = tempfile.TemporaryDirectory()
atexit.register(_td.cleanup)
_conf = Path(_td.name) / 'c'
_conf.write_text('STATE_DB=%s/x.db\nLOCAL_AI_ENABLED=false\n' % _td.name)
os.environ['RACKMARSHAL_CONFIG'] = str(_conf)

from rackmarshal.domains.backup import comparator  # noqa: E402

GOOD = {"status": "OK", "finished": True, "dest_exists": True, "pool_mounted": True,
        "latest_log_age_s": 3600, "log_error": False}
KEY = "BACKUP_RSYNC_FILEBACKUPS_CHECK"


def run(probe, value=None):
    env = {} if value is None else {KEY: value}
    with mock.patch.dict(os.environ, env, clear=False):
        if value is None:
            os.environ.pop(KEY, None)
        with mock.patch("pathlib.Path.is_file", return_value=False):
            return comparator.rsync_filebackups_results(probe)


class RsyncCheckIsOptIn(unittest.TestCase):
    def test_off_by_default_even_when_section_missing(self):
        self.assertEqual(run({"phones": {}}), [])
        self.assertEqual(run({"rsync_filebackups": GOOD}), [])

    def test_falsey_values_stay_off(self):
        for v in ("0", "false", "no", "off", "", "maybe"):
            self.assertEqual(run({"phones": {}}, v), [], v)

    def test_on_and_healthy(self):
        for v in ("1", "true", "YES", " on "):
            out = run({"rsync_filebackups": GOOD}, v)
            self.assertEqual([r["outcome"] for r in out], ["MATCH"], v)

    def test_on_and_section_missing_is_reported(self):
        out = run({"phones": {}}, "true")
        self.assertEqual(out[0]["outcome"], "STATUS-CHANGED")
        self.assertEqual(out[0]["changes"][0]["actual"], "missing_probe")

    def test_on_and_unhealthy_is_reported(self):
        out = run({"rsync_filebackups": dict(GOOD, status="FAILED")}, "true")
        self.assertEqual(out[0]["outcome"], "STATUS-CHANGED")

    def test_probe_error_or_absent_gives_nothing(self):
        self.assertEqual(run({"_error": "ssh_exit=255"}, "true"), [])
        self.assertEqual(run(None, "true"), [])


if __name__ == "__main__":
    unittest.main()
