import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class InstallerContractTests(unittest.TestCase):
 def test_installer_validates_before_migrations(self):
  s=(ROOT/'scripts/install.sh').read_text(); self.assertLess(s.index('rackmarshal validate-config'),s.index('rackmarshal.db.migrations.migrate'))
 def test_domain_units_are_installed(self):
  s=(ROOT/'scripts/install.sh').read_text(); self.assertIn('rackmarshal-domain@.service',s); self.assertIn('rackmarshal-domain@.timer',s); self.assertIn('ENABLED_DOMAINS',s)
 def test_uninstall_removes_domain_units(self):
  s=(ROOT/'scripts/uninstall.sh').read_text(); self.assertIn('rackmarshal-domain@.service',s); self.assertIn('rackmarshal-domain@.timer',s)
