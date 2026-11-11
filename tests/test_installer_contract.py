import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class InstallerContractTests(unittest.TestCase):
 def test_installer_validates_before_migrations(self):
  s=(ROOT/'scripts/install.sh').read_text(); self.assertLess(s.index('rackmarshal.cli validate-config'),s.index('rackmarshal.db.migrations.migrate'))
 def test_domain_units_are_installed(self):
  s=(ROOT/'scripts/install.sh').read_text(); self.assertIn('rackmarshal-domain@.service',s); self.assertIn('rackmarshal-domain@.timer',s); self.assertIn('ENABLED_DOMAINS',s)
 def test_uninstall_removes_domain_units(self):
  s=(ROOT/'scripts/uninstall.sh').read_text(); self.assertIn('rackmarshal-domain@.service',s); self.assertIn('rackmarshal-domain@.timer',s)
 def test_uninstall_removes_leftover_lifecycle_guards(self):
  import subprocess,tempfile,re
  from pathlib import Path as P
  text=(ROOT/'scripts/uninstall.sh').read_text()
  snippet=re.search(r'UNIT_ROOT=.*?shopt -u nullglob\n',text,re.S).group(0)
  with tempfile.TemporaryDirectory() as tmp:
   keep=P(tmp)/'rackmarshal-status.service.d';keep.mkdir();(keep/'99-lifecycle-maintenance.conf').write_text('[Unit]\n')
   other=P(tmp)/'rackmarshal-domain@.service.d';other.mkdir();(other/'99-lifecycle-maintenance.conf').write_text('x');(other/'20-cycle-health.conf').write_text('y')
   subprocess.run(['bash','-c',snippet],env={'RACKMARSHAL_UNIT_ROOT':tmp,'PATH':'/usr/bin:/bin'},check=True)
   self.assertFalse(keep.exists())
   self.assertEqual([p.name for p in other.iterdir()],['20-cycle-health.conf'])
