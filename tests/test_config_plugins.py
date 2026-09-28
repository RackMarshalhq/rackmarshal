import tempfile, tomllib, unittest
from pathlib import Path
from rackmarshal.cli import DOMAINS, ROOT, validate
class ConfigPluginTests(unittest.TestCase):
 def test_every_domain_manifest(self):
  for d in DOMAINS:
   data=tomllib.loads((ROOT/'domains'/d/'plugin.toml').read_text())
   self.assertEqual(data['id'].lower(),d)
   self.assertEqual(data['schema_version'],1)
   self.assertIn('run_cycle',data['entrypoints'])
 def test_enabled_domain_requires_site_config(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'c'; p.write_text('STATE_DB=/tmp/x\nENABLED_DOMAINS=zfs\n')
   errors=validate(p)
   self.assertTrue(any('ZFS_SSH_HOST' in e for e in errors))
 def test_generic_base_config_validates(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'c'; p.write_text('STATE_DB=/tmp/x\n')
   self.assertEqual(validate(p),[])
