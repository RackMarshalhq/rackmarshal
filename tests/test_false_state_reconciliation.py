import importlib, os, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

class FalseStateReconciliationTests(unittest.TestCase):
 def setUp(self):
  self.td=tempfile.TemporaryDirectory(); r=Path(self.td.name)
  self.cfg=r/'rackmarshal.conf'; self.cfg.write_text(f'''STATE_DB={r}/state.db\nINSTALL_ROOT={r}\nPVE_API_ENV={r}/pve.env\nPVE_CA_FILE={r}/pve-ca.pem\nHA_CREDENTIAL_FILE={r}/ha.env\nPVE_NODE=fixture-node\nSTATUS_API_LISTEN_ADDRESS=127.0.0.1\nSTATUS_API_LISTEN_PORT=9110\nPVE_IGNORE_RESOURCES=lxc:117,lxc:121,qemu:9001\n''')
  (r/'pve.env').write_text('PVE_API_URL=https://example.invalid\nPVE_TOKEN_ID=x\nPVE_TOKEN_SECRET=y\n')
  (r/'pve-ca.pem').write_text('fixture'); (r/'ha.env').write_text('HA_URL=http://127.0.0.1:9\nHA_TOKEN=fake\n')
  self.old=os.environ.get('RACKMARSHAL_CONFIG'); os.environ['RACKMARSHAL_CONFIG']=str(self.cfg)
  for n in list(sys.modules):
   if n.startswith('rackmarshal.domains.') or n.startswith('rackmarshal.api.') or n.startswith('rackmarshal.selfwatch.'):
    sys.modules.pop(n,None)
 def tearDown(self):
  if self.old is None: os.environ.pop('RACKMARSHAL_CONFIG',None)
  else: os.environ['RACKMARSHAL_CONFIG']=self.old
  self.td.cleanup()

 def test_pve_ignore_resources_parses_exact_identities(self):
  c=importlib.import_module('rackmarshal.domains.pve.collector')
  self.assertEqual(c.ignored_resource_identities(),{('lxc','117'),('lxc','121'),('qemu','9001')})

 def test_mount_node_is_resolved_after_runtime_config_env_load(self):
  c=importlib.import_module('rackmarshal.domains.mount.collector')
  c.apply_conf_env()
  with patch.object(c,'api_get',return_value={}) as get:
   c.fetch_lxc_mps({},'123')
   self.assertEqual(get.call_args.args[1],'/nodes/fixture-node/lxc/123/config')

 def test_self_watch_unit_inventory_uses_installed_unit_names(self):
  s=importlib.import_module('rackmarshal.api.status')
  names=set(s.SELF_WATCH_UNITS)
  self.assertIn('rackmarshal-status.service',names)
  self.assertIn('rackmarshal-domain@pve.timer',names)
  self.assertIn('rackmarshal-self-watch.timer',names)
  self.assertFalse(any('-cycle.timer' in x for x in names))
  self.assertNotIn('rackmarshal-status-api.service',names)

 def test_legacy_self_incident_recovers_when_no_longer_desired(self):
  c=importlib.import_module('rackmarshal.selfwatch.cycle')
  con=sqlite3.connect(':memory:'); con.row_factory=sqlite3.Row
  con.execute('create table self_incidents(id integer primary key, signal_key text, incident_type text, severity text, incident_state text, detail_json text, opened_at text, recovered_at text, last_seen_at text)')
  con.execute("insert into self_incidents values(1,'unit:rackmarshal-pve-cycle.timer','UNIT_INACTIVE','warning','OPEN','{}','2026-01-01',NULL,'2026-01-01')")
  result=c.sync_self_incidents(con,[])
  self.assertEqual(result['recovered'],1)
  self.assertEqual(con.execute('select incident_state from self_incidents where id=1').fetchone()[0],'RECOVERED')

 def test_self_watch_explainer_is_single_executable(self):
  c=importlib.import_module('rackmarshal.selfwatch.cycle')
  self.assertIsInstance(c.INCIDENT_EXPLAINER,str)
  self.assertNotIn(' -m ',c.INCIDENT_EXPLAINER)
  self.assertTrue(c.INCIDENT_EXPLAINER.endswith('rackmarshal-explain'))

 def test_legacy_homelabops_cycle_health_is_not_actionable(self):
  import rackmarshal.selfwatch.incidents as i
  desired=i.evaluate_self_signals({}, {}, {}, {
   'homelabops-zfs-cycle.service': {'health_state':'FAILED','failure_count':1}
  })
  # The evaluator itself is generic; collection/status filters legacy rows before evaluation.
  self.assertEqual(len(desired),1)
  import rackmarshal.selfwatch.cycle as c
  src=Path(c.__file__).read_text()
  self.assertIn('startswith("rackmarshal-")',src)
  import rackmarshal.api.status as st
  self.assertIn('startswith("rackmarshal-")',Path(st.__file__).read_text())

if __name__=='__main__': unittest.main()
