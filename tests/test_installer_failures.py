import tempfile,unittest
from pathlib import Path
from rackmarshal.cli import validate
class InstallerFailureTests(unittest.TestCase):
 def test_unknown_domain_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'c'; p.write_text('STATE_DB=/tmp/x\nENABLED_DOMAINS=fictional\n'); self.assertTrue(any('unknown enabled domains' in e for e in validate(p)))
 def test_hardware_missing_dynamic_inventory_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); key=p/'key'; kh=p/'kh'; key.write_text('x'); kh.write_text('x'); key.chmod(0o600); kh.chmod(0o600)
   c=p/'c'; c.write_text(f'''STATE_DB=/tmp/x\nSITE_NAME=fictional\nENABLED_DOMAINS=hardware\nHARDWARE_SSH_HOST=host.invalid\nHARDWARE_SSH_USER=observer\nHARDWARE_SSH_KEY={key}\nHARDWARE_KNOWN_HOSTS={kh}\nHARDWARE_NVME_SERIALS=FAKE001\nHARDWARE_HOT_THRESHOLD_C=60\nHARDWARE_HOT_REQUIRED_SAMPLES=2\nHARDWARE_URGENT_THRESHOLD_C=75\nHARDWARE_RECOVERY_THRESHOLD_C=55\nHARDWARE_RECOVERY_REQUIRED_SAMPLES=2\n'''); e=validate(c); self.assertTrue(any('HARDWARE_NVME_FAKE001_MODEL' in x for x in e)); self.assertTrue(any('HARDWARE_NVME_FAKE001_ROLE' in x for x in e))
 def test_broad_secret_permissions_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); cred=p/'ha.env'; cred.write_text('HA_URL=x\nHA_TOKEN=y\n'); cred.chmod(0o644); c=p/'c'; c.write_text(f'STATE_DB=/tmp/x\nENABLED_DOMAINS=ha\nHA_CREDENTIAL_FILE={cred}\n'); self.assertTrue(any('permissions are too broad' in e for e in validate(c)))
