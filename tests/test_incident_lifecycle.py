import importlib, json, os, sqlite3, tempfile, unittest
from pathlib import Path
class IncidentLifecycleTests(unittest.TestCase):
 def setUp(self):
  self.td=tempfile.TemporaryDirectory(); self.root=Path(self.td.name); self.db=self.root/'state.db'; self.conf=self.root/'rackmarshal.conf'
  self.conf.write_text(f'STATE_DB={self.db}\nSITE_NAME=fictional\nHARDWARE_HOT_THRESHOLD_C=60\nHARDWARE_HOT_REQUIRED_SAMPLES=2\nHARDWARE_URGENT_THRESHOLD_C=75\nHARDWARE_RECOVERY_THRESHOLD_C=55\nHARDWARE_RECOVERY_REQUIRED_SAMPLES=2\n')
  os.environ['RACKMARSHAL_CONFIG']=str(self.conf); os.environ['RACKMARSHAL_STATE_DB']=str(self.db)
  import rackmarshal.core.config as cfg; cfg.DEFAULT_CONFIG_FILE=self.conf
  cfg.state_db.__defaults__ = (None,)
  from rackmarshal.db.migrations import migrate
  old=os.sys.argv; os.sys.argv=['migrate','--db',str(self.db),'--apply','--yes']
  try: migrate.main()
  finally: os.sys.argv=old
 def tearDown(self):
  import sys
  import rackmarshal.core.config as cfg; cfg.DEFAULT_CONFIG_FILE=Path(os.environ.get('RACKMARSHAL_CONFIG','/etc/rackmarshal/rackmarshal.conf'))
  for n in list(sys.modules):
   if n.startswith('rackmarshal.domains.') and (n.endswith('.incidents') or n.endswith('.comparator')): sys.modules.pop(n,None)
  self.td.cleanup()
 def test_mount_open_recover(self):
  m=importlib.import_module('rackmarshal.domains.mount.incidents')
  con=sqlite3.connect(self.db); con.row_factory=sqlite3.Row; now='2026-01-01T00:00:00Z'
  bad={'results':[{'id':'fictional-mount','guest_kind':'host','guest_id':'','mountpoint':'/mnt/fictional','state':'missing','severity_missing':'critical','optional':False,'expected_source':'fictional:/share','observed_source':None,'fstype':'nfs'}]}
  con.execute('insert into mount_observations(observed_at,source,schema_version,checked_count,ok_count,problem_count,payload_json) values(?,?,?,?,?,?,?)',(now,'fictional',1,1,0,1,json.dumps(bad))); con.commit(); r=m.process(con); self.assertEqual(r['opened'],1)
  for index, missing in enumerate(({'results':[]}, {'results':[{'id':'fictional-mount','state':'unknown'}]})):
   con.execute('insert into mount_observations(observed_at,source,schema_version,checked_count,ok_count,problem_count,payload_json) values(?,?,?,?,?,?,?)',(f'2026-01-01T00:0{index+1}:00Z','fictional',1,0,0,0,json.dumps(missing)));con.commit()
   r=m.process(con);self.assertEqual(r['recovered'],0);self.assertEqual(r['open_problems'],1)
   self.assertEqual(con.execute("select count(*) from mount_incidents where incident_state='OPEN'").fetchone()[0],1)
  good={'results':[{'id':'fictional-mount','guest_kind':'host','guest_id':'','mountpoint':'/mnt/fictional','state':'ok','optional':False,'expected_source':'fictional:/share','observed_source':'fictional:/share','fstype':'nfs'}]}
  con.execute('insert into mount_observations(observed_at,source,schema_version,checked_count,ok_count,problem_count,payload_json) values(?,?,?,?,?,?,?)',('2026-01-01T00:05:00Z','fictional',1,1,1,0,json.dumps(good))); con.commit(); r=m.process(con); self.assertEqual(r['recovered'],1); self.assertEqual(con.execute("select count(*) from mount_incidents where incident_state='OPEN'").fetchone()[0],0); con.close()
 def test_hardware_open_recover(self):
  h=importlib.import_module('rackmarshal.domains.hardware.incidents'); h=importlib.reload(h); con=sqlite3.connect(self.db); con.row_factory=sqlite3.Row; h.ensure_device_state_table(con); h.ensure_cursor(con)
  def row(i,status,temp): return {'id':i,'serial':'FAKE001','role':'test','model':'Fictional NVMe','temperature_c':temp,'observed_at':f'2026-01-01T00:0{i}:00Z','status':status}
  h.process_observation(con,row(1,'URGENT',80)); con.commit(); self.assertEqual(con.execute("select count(*) from hardware_incidents where incident_state='OPEN'").fetchone()[0],1)
  h.process_observation(con,row(2,'OK',40)); h.process_observation(con,row(3,'OK',40)); con.commit(); self.assertEqual(con.execute("select count(*) from hardware_incidents where incident_state='OPEN'").fetchone()[0],0); self.assertEqual(con.execute("select count(*) from hardware_incidents where incident_state='RECOVERED'").fetchone()[0],1); con.close()
 def test_zfs_open_recover(self):
  z=importlib.import_module('rackmarshal.domains.zfs.incidents'); con=sqlite3.connect(self.db); now='2026-01-01T01:00:00Z'
  con.execute('insert into zfs_observations(observed_at,source,schema_version,host_key_verified,pool_count,payload_json) values(?,?,?,?,?,?)',(now,'fictional',1,1,1,'{}')); oid=con.execute('select last_insert_rowid()').fetchone()[0]
  con.execute("insert into zfs_events(observation_id,resource_type,resource_key,pool_name,vdev_name,outcome,baseline_state,changes_json,observed_at) values(?,?,?,?,?,?,?,?,?)",(oid,'zfs_pool','fictional-pool','fictional-pool',None,'STATUS-CHANGED','VERIFIED','{}',now)); con.commit(); con.close()
  import subprocess,sys
  bad={'schema_version':1,'comparator':'zfs_baseline','observation_id':oid,'observed_at':now,'results':[{'resource_type':'zfs_pool','resource_key':'fictional-pool','outcome':'STATUS-CHANGED','baseline_state':'VERIFIED'}]}
  subprocess.run([sys.executable,'-m','rackmarshal.domains.zfs.incidents','--database',str(self.db)],input=json.dumps(bad),text=True,check=True,capture_output=True)
  con=sqlite3.connect(self.db); self.assertEqual(con.execute("select count(*) from zfs_incidents where incident_state='OPEN'").fetchone()[0],1); con.close()
  now2='2026-01-01T01:05:00Z'; con=sqlite3.connect(self.db); con.execute('insert into zfs_observations(observed_at,source,schema_version,host_key_verified,pool_count,payload_json) values(?,?,?,?,?,?)',(now2,'fictional',1,1,1,'{}')); oid2=con.execute('select last_insert_rowid()').fetchone()[0]; con.commit(); con.close()
  good={'schema_version':1,'comparator':'zfs_baseline','observation_id':oid2,'observed_at':now2,'results':[{'resource_type':'zfs_pool','resource_key':'fictional-pool','outcome':'MATCH','baseline_state':'VERIFIED'}]}
  subprocess.run([sys.executable,'-m','rackmarshal.domains.zfs.incidents','--database',str(self.db)],input=json.dumps(good),text=True,check=True,capture_output=True)
  con=sqlite3.connect(self.db); self.assertEqual(con.execute("select count(*) from zfs_incidents where incident_state='OPEN'").fetchone()[0],0); self.assertEqual(con.execute("select count(*) from zfs_incidents where incident_state='RECOVERED'").fetchone()[0],1); con.close()
 def _insert_obs(self,collector,at):
  con=sqlite3.connect(self.db); con.execute('insert into observations(collector,observed_at,source,schema_version,tls_verified,resource_count,payload_json) values(?,?,?,?,?,?,?)',(collector,at,'fictional',1,1,1,'{}')); oid=con.execute('select last_insert_rowid()').fetchone()[0]; con.commit(); con.close(); return oid
 def test_backup_open_recover(self):
  import subprocess,sys
  oid0=self._insert_obs('backup_domain','2026-01-01T02:00:00Z'); con=sqlite3.connect(self.db); con.execute("insert into backup_incident_processing(observation_id,processing_kind,note) values(?,'BOOTSTRAP','fixture')",(oid0,)); con.commit(); con.close()
  oid=self._insert_obs('backup_domain','2026-01-01T02:05:00Z'); con=sqlite3.connect(self.db); con.execute("insert into backup_events(observation_id,resource_type,resource_key,outcome,baseline_state,changes_json,observed_at) values(?,?,?,?,?,?,?)",(oid,'backup_guest','fictional-guest','STATUS-CHANGED','VERIFIED','[]','2026-01-01T02:05:00Z')); con.commit(); con.close()
  bad={'schema_version':1,'comparator':'backup_baseline','observation_id':oid,'observed_at':'2026-01-01T02:05:00Z','results':[{'resource_type':'backup_guest','resource_key':'fictional-guest','display_name':'Fictional Guest','outcome':'STATUS-CHANGED','baseline_state':'VERIFIED','changes':[]}]}
  subprocess.run([sys.executable,'-m','rackmarshal.domains.backup.incidents','--database',str(self.db)],input=json.dumps(bad),text=True,check=True,capture_output=True); con=sqlite3.connect(self.db); self.assertEqual(con.execute("select count(*) from backup_incidents where incident_state='OPEN'").fetchone()[0],1); con.close()
  oid2=self._insert_obs('backup_domain','2026-01-01T02:10:00Z'); good={'schema_version':1,'comparator':'backup_baseline','observation_id':oid2,'observed_at':'2026-01-01T02:10:00Z','results':[{'resource_type':'backup_guest','resource_key':'fictional-guest','display_name':'Fictional Guest','outcome':'MATCH','baseline_state':'VERIFIED','changes':[]}]}
  subprocess.run([sys.executable,'-m','rackmarshal.domains.backup.incidents','--database',str(self.db)],input=json.dumps(good),text=True,check=True,capture_output=True); con=sqlite3.connect(self.db); self.assertEqual(con.execute("select count(*) from backup_incidents where incident_state='OPEN'").fetchone()[0],0); self.assertEqual(con.execute("select count(*) from backup_incidents where incident_state='RECOVERED'").fetchone()[0],1); con.close()
 def test_pve_open_recover(self):
  p=importlib.import_module('rackmarshal.domains.pve.incidents'); oid0=self._insert_obs('pve_cluster_resources','2026-01-01T03:00:00Z'); con=sqlite3.connect(self.db); con.execute("insert into incident_processing(observation_id,processing_kind,note) values(?,'BOOTSTRAP','fixture')",(oid0,)); con.commit(); con.close(); oid=self._insert_obs('pve_cluster_resources','2026-01-01T03:05:00Z')
  p.run_comparator=lambda x:{'schema_version':1,'comparator':'pve_resource_baseline','observation_id':x,'differences':[{'resource_type':'qemu','resource_key':'9001','display_name':'Fictional VM','result':'STATUS-CHANGED','baseline_state':'VERIFIED','expected_status':'running','actual_status':'stopped','note':''}]}; r=p.process(oid); self.assertEqual(r['incidents_opened'],1)
  oid2=self._insert_obs('pve_cluster_resources','2026-01-01T03:10:00Z'); p.run_comparator=lambda x:{'schema_version':1,'comparator':'pve_resource_baseline','observation_id':x,'differences':[]}; r=p.process(oid2); self.assertEqual(r['incidents_recovered'],1); con=sqlite3.connect(self.db); self.assertEqual(con.execute("select count(*) from resource_incidents where incident_state='OPEN'").fetchone()[0],0); con.close()
 def test_ha_open_recover(self):
  import subprocess,sys
  oid0=self._insert_obs('home_assistant','2026-01-01T04:00:00Z'); con=sqlite3.connect(self.db); con.execute("insert into ha_resource_baseline(resource_key,resource_type,display_name,baseline_state,expected_status,source_observation_id) values(?,?,?,?,?,?)",('home_assistant_core','ha_core','Fictional Core','VERIFIED','RUNNING',oid0)); con.execute("insert into ha_incident_processing(observation_id,processing_kind,note) values(?,'BOOTSTRAP','fixture')",(oid0,)); con.commit(); con.close()
  oid=self._insert_obs('home_assistant','2026-01-01T04:05:00Z'); con=sqlite3.connect(self.db); con.execute("insert into ha_events(observation_id,resource_type,resource_key,outcome,baseline_state,changes_json,observed_at) values(?,?,?,?,?,?,?)",(oid,'ha_core','home_assistant_core','STATUS-CHANGED','VERIFIED','{}','2026-01-01T04:05:00Z')); con.commit(); con.close()
  env=dict(os.environ,RACKMARSHAL_FIXTURE_MODE='bad'); subprocess.run([sys.executable,'-m','rackmarshal.domains.ha.incidents','--db',str(self.db),'--comparator',str(Path(__file__).with_name('fixture_comparator.py'))],env=env,check=True,capture_output=True,text=True); con=sqlite3.connect(self.db); self.assertEqual(con.execute("select count(*) from ha_incidents where incident_state='OPEN'").fetchone()[0],1); con.close()
  self._insert_obs('home_assistant','2026-01-01T04:10:00Z'); env=dict(os.environ,RACKMARSHAL_FIXTURE_MODE='good'); subprocess.run([sys.executable,'-m','rackmarshal.domains.ha.incidents','--db',str(self.db),'--comparator',str(Path(__file__).with_name('fixture_comparator.py'))],env=env,check=True,capture_output=True,text=True); con=sqlite3.connect(self.db); self.assertEqual(con.execute("select count(*) from ha_incidents where incident_state='OPEN'").fetchone()[0],0); self.assertEqual(con.execute("select count(*) from ha_incidents where incident_state='RECOVERED'").fetchone()[0],1); con.close()
