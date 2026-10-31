import tempfile
import unittest
from pathlib import Path

from rackmarshal.cli import validate


def errors_for(mode, key="HA_CREDENTIAL_FILE", domain="ha"):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        cred = p / "cred"
        cred.write_text("HA_URL=x\nHA_TOKEN=y\n")
        cred.chmod(mode)
        conf = p / "c"
        conf.write_text(f"STATE_DB=/tmp/x\nENABLED_DOMAINS={domain}\n{key}={cred}\n")
        return [e for e in validate(conf) if "permissions are too broad" in e]


class CredentialPermissions(unittest.TestCase):
    def test_documented_group_readable_mode_is_accepted(self):
        self.assertEqual(errors_for(0o640), [])
        self.assertEqual(errors_for(0o600), [])
        self.assertEqual(errors_for(0o440), [])

    def test_group_write_or_any_access_for_others_is_rejected(self):
        for mode in (0o660, 0o620, 0o650, 0o644, 0o604, 0o602, 0o666, 0o700 | 0o010):
            self.assertTrue(errors_for(mode), oct(mode))

    def test_env_files_for_other_domains_follow_the_same_rule(self):
        self.assertEqual(errors_for(0o640, "PVE_API_ENV", "pve"), [])
        self.assertTrue(errors_for(0o644, "PVE_API_ENV", "pve"))
        self.assertEqual(errors_for(0o640, "PBS_API_ENV", "backup"), [])
        self.assertTrue(errors_for(0o660, "PBS_API_ENV", "backup"))

    def test_ssh_keys_still_require_owner_only(self):
        self.assertTrue(errors_for(0o640, "ZFS_SSH_KEY", "zfs"))
        self.assertTrue(errors_for(0o640, "ZFS_KNOWN_HOSTS", "zfs"))
        self.assertEqual(errors_for(0o600, "ZFS_SSH_KEY", "zfs"), [])


if __name__ == "__main__":
    unittest.main()
