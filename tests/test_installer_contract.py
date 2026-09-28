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

class LocalAIInstallerContractTests(unittest.TestCase):
 def test_local_ai_units_are_installed_and_removed(self):
  install=(ROOT/'scripts/install.sh').read_text(); uninstall=(ROOT/'scripts/uninstall.sh').read_text()
  self.assertIn('rackmarshal-local-ai-explain.service',install); self.assertIn('rackmarshal-local-ai-explain.timer',install)
  self.assertIn('LOCAL_AI_ENABLED',install); self.assertIn('rackmarshal-local-ai-explain.timer',uninstall)

class HomelabOpsMigrationContractTests(unittest.TestCase):
 def test_migration_and_rollback_tools_are_bundled(self):
  b=(ROOT/'scripts/build-installer-bundle.sh').read_text()
  self.assertIn('migrate-from-homelabops.sh',b); self.assertIn('rollback-to-homelabops.sh',b)
 def test_migration_preserves_legacy_state_before_switch(self):
  s=(ROOT/'scripts/migrate-from-homelabops.sh').read_text()
  self.assertIn('source-state.db',s); self.assertIn('source-state.sha256',s)
  self.assertIn('--no-start',s); self.assertIn('RACKMARSHAL_HOMELABOPS_MIGRATION_OK',s)
 def test_rollback_restores_recorded_units(self):
  s=(ROOT/'scripts/rollback-to-homelabops.sh').read_text()
  self.assertIn('enabled-units.txt',s); self.assertIn('active-units.txt',s)
  self.assertIn('RACKMARSHAL_HOMELABOPS_ROLLBACK_OK',s)

class ProductionParityTimerContractTests(unittest.TestCase):
 def test_maintenance_and_selfwatch_units_installed(self):
  s=(ROOT/'scripts/install.sh').read_text()
  for name in ('rackmarshal-self-watch.timer','rackmarshal-db-snapshot.timer','rackmarshal-evidence-export.timer','rackmarshal-observation-prune.timer'):
   self.assertIn(name,s)
 def test_maintenance_and_selfwatch_units_removed(self):
  s=(ROOT/'scripts/uninstall.sh').read_text()
  for name in ('rackmarshal-self-watch.timer','rackmarshal-db-snapshot.timer','rackmarshal-evidence-export.timer','rackmarshal-observation-prune.timer'):
   self.assertIn(name,s)

class RollbackIsolationContractTests(unittest.TestCase):
 def test_enabled_legacy_services_start_without_dependencies(self):
  s=(ROOT/'scripts/rollback-to-homelabops.sh').read_text()
  self.assertIn('systemctl cancel "$unit"', s)
  self.assertIn('systemd-run --unit="rackmarshal-rollback-', s)
  self.assertIn('systemctl is-active --quiet homelabops-status-api.service', s)
  self.assertIn('systemctl is-active --quiet rackmarshal-rollback-homelabops-status-api.service', s)

class DomainRuntimeLockContractTests(unittest.TestCase):
 def test_domain_unit_provides_private_runtime_directory(self):
  s=(ROOT/'packaging/systemd/rackmarshal-domain@.service').read_text()
  self.assertIn('RuntimeDirectory=rackmarshal',s)
  self.assertIn('RuntimeDirectoryMode=0750',s)
 def test_locking_domains_use_runtime_directory(self):
  for d in ('ha','hardware','zfs'):
   s=(ROOT/f'rackmarshal/domains/{d}/cycle.py').read_text()
   self.assertIn('/run/rackmarshal/',s,d)
   self.assertNotIn('/run/lock/',s,d)

class MigratedSSHKeyPermissionContractTests(unittest.TestCase):
 def test_migration_sets_private_observer_keys_owner_only(self):
  s=(ROOT/'scripts/migrate-from-homelabops.sh').read_text()
  self.assertIn("! -name '*.pub' ! -name 'known_hosts'",s)
  self.assertIn('chown rackmarshal:rackmarshal',s)
  self.assertIn('chmod 0600',s)
