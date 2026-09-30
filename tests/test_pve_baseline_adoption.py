from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('adoption',Path('scripts/adopt-pve-baseline.py'))
adoption=importlib.util.module_from_spec(spec);spec.loader.exec_module(adoption)

class PveBaselineAdoptionTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
  self.root=Path(self.directory.name);self.db=self.root/'fixture.db'
  self.now=datetime(2026,1,1,12,0,tzinfo=timezone.utc)
  with closing(sqlite3.connect(self.db)) as c:
   c.executescript(Path('rackmarshal/db/migrations/001_pve_ledger.sql').read_text())
   payload={'resources':[{'type':'lxc','vmid':9001,'name':'Fixture A','status':'stopped'},{'type':'lxc','vmid':9002,'name':'Fixture B','status':'running'}]}
   c.execute('INSERT INTO observations(id,collector,observed_at,source,schema_version,tls_verified,resource_count,payload_json) VALUES(1,?,?,?,?,?,?,?)',('pve_cluster_resources','2026-01-01T11:59:00Z','fixture',1,1,2,json.dumps(payload)))
   c.execute("INSERT INTO resource_baseline(resource_type,resource_key,expected_status,baseline_state) VALUES('qemu','9999','running','VERIFIED')")
   c.commit()
 def call(self, resources=None, apply=False):
  return adoption.adopt(self.db,1,resources or ['lxc:9001','lxc:9002'],'User authorized fixture baseline',apply,self.root,self.now)
 def count(self):
  with closing(sqlite3.connect(self.db)) as c:return c.execute('SELECT COUNT(*) FROM resource_baseline').fetchone()[0]
 def test_plan_does_not_write(self):
  self.assertEqual(self.call()['state'],'PLANNED');self.assertEqual(self.count(),1)
 def test_apply_preserves_unselected_baseline_and_backs_up(self):
  r=self.call(apply=True);self.assertEqual(self.count(),3)
  self.assertEqual([x['expected_status'] for x in r['rows']],['stopped','running'])
  with closing(sqlite3.connect(r['backup'])) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM resource_baseline').fetchone()[0],1)
  with closing(sqlite3.connect(self.db)) as c:
   self.assertEqual(c.execute("SELECT expected_status FROM resource_baseline WHERE resource_key='9999'").fetchone()[0],'running')
   self.assertEqual(c.execute('SELECT source_observation FROM resource_baseline WHERE resource_type=\'lxc\'').fetchall(),[(1,),(1,)])
 def test_missing_resource_prevents_partial_batch(self):
  with self.assertRaises(ValueError):self.call(['lxc:9001','lxc:9003'],True)
  self.assertEqual(self.count(),1)
 def test_existing_baseline_cannot_be_overwritten(self):
  with closing(sqlite3.connect(self.db)) as c:
   c.execute("INSERT INTO resource_baseline(resource_type,resource_key,expected_status,baseline_state) VALUES('lxc','9001','running','VERIFIED')");c.commit()
  with self.assertRaisesRegex(ValueError,'must not be overwritten'):self.call(['lxc:9001'],True)
  self.assertEqual(self.count(),2)
  with closing(sqlite3.connect(self.db)) as c:self.assertEqual(c.execute("SELECT expected_status FROM resource_baseline WHERE resource_key='9001'").fetchone()[0],'running')
 def test_database_failure_rolls_back_every_insert(self):
  with closing(sqlite3.connect(self.db)) as c:
   c.execute("CREATE TRIGGER reject_second BEFORE INSERT ON resource_baseline WHEN NEW.resource_key='9002' BEGIN SELECT RAISE(ABORT,'fixture rejection'); END");c.commit()
  with self.assertRaises(sqlite3.IntegrityError):self.call(apply=True)
  self.assertEqual(self.count(),1)
 def test_duplicate_scope_rejected(self):
  with self.assertRaises(ValueError):self.call(['lxc:9001','lxc:9001'],True)
  self.assertEqual(self.count(),1)
 def test_stale_observation_rejected(self):
  with closing(sqlite3.connect(self.db)) as c:c.execute("UPDATE observations SET observed_at='2026-01-01T10:00:00Z'");c.commit()
  with self.assertRaises(ValueError):self.call(apply=True)
  self.assertEqual(self.count(),1)
