import sqlite3, unittest
from rackmarshal.api.v1 import canon, get_evidence, list_incidents, material_changes, parse_id, route

SCHEMA='''
CREATE TABLE resource_incidents(id INTEGER PRIMARY KEY,resource_type TEXT,resource_key TEXT,display_name TEXT,incident_type TEXT,incident_state TEXT,baseline_state TEXT,opened_observation_id INTEGER,last_abnormal_observation_id INTEGER,recovered_observation_id INTEGER,opened_at TEXT,last_abnormal_at TEXT,recovered_at TEXT,occurrence_count INTEGER,opening_changes_json TEXT,latest_changes_json TEXT);
CREATE TABLE zfs_incidents(id INTEGER PRIMARY KEY,resource_type TEXT,resource_key TEXT,pool_name TEXT,vdev_name TEXT,incident_type TEXT,incident_state TEXT,baseline_state TEXT,opened_observation_id INTEGER,last_abnormal_observation_id INTEGER,recovered_observation_id INTEGER,opened_at TEXT,last_abnormal_at TEXT,recovered_at TEXT,occurrence_count INTEGER,opening_changes_json TEXT,latest_changes_json TEXT);
CREATE TABLE backup_incidents AS SELECT * FROM resource_incidents WHERE 0;
CREATE TABLE ha_incidents AS SELECT * FROM resource_incidents WHERE 0;
CREATE TABLE hardware_incidents(id INTEGER PRIMARY KEY,serial TEXT,role TEXT,model TEXT,incident_type TEXT,severity TEXT,incident_state TEXT,opened_observation_id INTEGER,last_abnormal_observation_id INTEGER,recovered_observation_id INTEGER,opened_at TEXT,last_abnormal_at TEXT,recovered_at TEXT,occurrence_count INTEGER,opening_changes_json TEXT,latest_changes_json TEXT);
CREATE TABLE mount_incidents(id INTEGER PRIMARY KEY,mount_id TEXT,incident_type TEXT,severity TEXT,incident_state TEXT,opened_observation_id INTEGER,last_abnormal_observation_id INTEGER,recovered_observation_id INTEGER,opened_at TEXT,last_abnormal_at TEXT,recovered_at TEXT,occurrence_count INTEGER,opening_changes_json TEXT,latest_changes_json TEXT);
CREATE TABLE observations(id INTEGER PRIMARY KEY,collector TEXT,observed_at TEXT,source TEXT,schema_version INTEGER,recorded_at TEXT,payload_json TEXT);
CREATE TABLE zfs_observations(id INTEGER PRIMARY KEY,observed_at TEXT,source TEXT,schema_version INTEGER,recorded_at TEXT,payload_json TEXT);
CREATE TABLE hardware_observations(id INTEGER PRIMARY KEY,observed_at TEXT,host TEXT,recorded_at TEXT);
CREATE TABLE mount_observations(id INTEGER PRIMARY KEY,observed_at TEXT,source TEXT,schema_version INTEGER,recorded_at TEXT,payload_json TEXT);
'''
for t in ('resource_events','zfs_events','backup_events','ha_events'):
 SCHEMA+=f'CREATE TABLE {t}(id INTEGER PRIMARY KEY,observation_id INTEGER,resource_type TEXT,resource_key TEXT,event_type TEXT,outcome TEXT,baseline_state TEXT,observed_at TEXT,detected_at TEXT,changes_json TEXT);\n'
SCHEMA+='CREATE TABLE hardware_events(id INTEGER PRIMARY KEY,observation_id INTEGER,serial TEXT,outcome TEXT,observed_at TEXT,changes_json TEXT); CREATE TABLE mount_events(id INTEGER PRIMARY KEY,observation_id INTEGER,mount_id TEXT,outcome TEXT,observed_at TEXT,changes_json TEXT);'

class ApiV1Contract(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:'); self.db.row_factory=sqlite3.Row; self.db.executescript(SCHEMA)
  self.db.execute("INSERT INTO resource_incidents VALUES(1,'qemu','100','HA','MISSING','OPEN','VERIFIED',10,11,NULL,'2026-09-29T01:00:00Z','2026-09-29T02:00:00Z',NULL,2,NULL,NULL)")
  self.db.execute("INSERT INTO zfs_incidents VALUES(1,'zfs_pool','data','data',NULL,'STATUS-CHANGED','RECOVERED','VERIFIED',20,21,22,'2026-09-28T01:00:00Z','2026-09-28T02:00:00Z','2026-09-28T03:00:00Z',1,'{}','{}')")
  self.db.execute("INSERT INTO zfs_observations VALUES(22,'2026-09-28T03:00:00Z','ms01',1,'2026-09-28T03:00:01Z','{\"token\":\"SECRET\"}')")
 def tearDown(self): self.db.close()
 def test_canonical_ids_are_domain_unique(self): self.assertNotEqual(canon('PVE',1),canon('ZFS',1))
 def test_numeric_incident_id_rejected(self):
  with self.assertRaisesRegex(ValueError,'INVALID_ID'): parse_id('1')
 def test_nullable_severity_not_invented(self):
  items,_=list_incidents(self.db,{'domain':'PVE'}); self.assertIsNone(items[0]['severity'])
 def test_recovery_evidence(self):
  items,_=list_incidents(self.db,{'domain':'ZFS','state':'RECOVERED'}); self.assertIn('observation:ZFS:22',items[0]['evidence_refs'])
 def test_raw_payload_redacted(self):
  ev=get_evidence(self.db,'observation:ZFS:22'); self.assertNotIn('SECRET',str(ev)); self.assertNotIn('payload_json',str(ev))
 def test_pagination_and_bad_cursor(self):
  code,payload=route(self.db,'/v1/incidents',{'limit':'1'}); self.assertEqual(code,200); self.assertEqual(payload['meta']['limit'],1)
  code,payload=route(self.db,'/v1/incidents',{'cursor':'bad!'}); self.assertEqual(code,400); self.assertEqual(payload['error']['code'],'INVALID_CURSOR')
 def test_health_envelope(self):
  code,p=route(self.db,'/v1/health',{}); self.assertEqual((code,p['api_version'],p['data']['database_readable']),(200,'v1',True))
 def test_material_changes_collapse_repeated_polling_per_resource(self):
  rows=[
   (1,101,'backup_phone','olivia','STATUS-CHANGED',None,'VERIFIED','2026-09-29T20:00:00Z',None,'[{"field":"phone_age_hours","actual":170,"expected":"<= 168.0"}]'),
   (2,102,'backup_phone','preston','STATUS-CHANGED',None,'VERIFIED','2026-09-29T20:01:00Z',None,'[{"field":"phone_age_hours","actual":180,"expected":"<= 168.0"}]'),
   (3,103,'backup_phone','olivia','STATUS-CHANGED',None,'VERIFIED','2026-09-29T20:05:00Z',None,'[{"field":"phone_age_hours","actual":175,"expected":"<= 168.0"}]'),
   (4,104,'backup_phone','preston','STATUS-CHANGED',None,'VERIFIED','2026-09-29T20:06:00Z',None,'[{"field":"phone_age_hours","actual":185,"expected":"<= 168.0"}]')]
  self.db.executemany('INSERT INTO backup_events VALUES(?,?,?,?,?,?,?,?,?,?)',rows)
  items,meta=material_changes(self.db,{'domain':'BACKUP','observed_after':'2026-09-29T20:00:00Z','observed_before':'2026-09-29T21:00:00Z','limit':'20'})
  self.assertEqual(meta['raw_event_count'],4); self.assertEqual(meta['material_change_count'],2); self.assertEqual(meta['collapsed_event_count'],2)
  by_key={x['resource_key']:x for x in items}; self.assertEqual(by_key['olivia']['repeat_count'],2); self.assertEqual(by_key['olivia']['first_changes'][0]['actual'],170); self.assertEqual(by_key['olivia']['latest_changes'][0]['actual'],175)
 def test_material_changes_preserve_transition_away_and_back(self):
  rows=[
   (10,110,'backup_phone','olivia','STATUS-CHANGED',None,'VERIFIED','2026-09-29T20:00:00Z',None,'[{"field":"phone_age_hours","actual":170,"expected":"<= 168.0"}]'),
   (11,111,'backup_phone','olivia','RECOVERED',None,'VERIFIED','2026-09-29T20:10:00Z',None,'[{"field":"status","actual":"OK","expected":"OK"}]'),
   (12,112,'backup_phone','olivia','STATUS-CHANGED',None,'VERIFIED','2026-09-29T20:20:00Z',None,'[{"field":"phone_age_hours","actual":170,"expected":"<= 168.0"}]')]
  self.db.executemany('INSERT INTO backup_events VALUES(?,?,?,?,?,?,?,?,?,?)',rows)
  items,meta=material_changes(self.db,{'domain':'BACKUP','limit':'20'})
  self.assertEqual(meta['material_change_count'],3); self.assertEqual([x['event_type'] for x in reversed(items)],['STATUS-CHANGED','RECOVERED','STATUS-CHANGED'])
if __name__=='__main__': unittest.main()
