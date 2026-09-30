import sqlite3, unittest
from rackmarshal.api.v1 import incident_timeline,incident_evidence_bundle,route

SCHEMA="""
CREATE TABLE observations(id INTEGER PRIMARY KEY,collector TEXT,observed_at TEXT,source TEXT,schema_version INTEGER,recorded_at TEXT,payload_json TEXT);
CREATE TABLE backup_events(id INTEGER PRIMARY KEY,observation_id INTEGER,resource_type TEXT,resource_key TEXT,outcome TEXT,baseline_state TEXT,changes_json TEXT,observed_at TEXT,recorded_at TEXT);
CREATE TABLE backup_incidents(id INTEGER PRIMARY KEY,resource_type TEXT,resource_key TEXT,display_name TEXT,incident_type TEXT,incident_state TEXT,baseline_state TEXT,opened_event_id INTEGER,last_event_id INTEGER,opened_observation_id INTEGER,last_abnormal_observation_id INTEGER,recovered_observation_id INTEGER,opened_at TEXT,last_abnormal_at TEXT,recovered_at TEXT,occurrence_count INTEGER,opening_changes_json TEXT,latest_changes_json TEXT,note TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE resource_events(id INTEGER PRIMARY KEY,observation_id INTEGER,event_type TEXT,resource_type TEXT,resource_key TEXT,display_name TEXT,baseline_state TEXT,expected_status TEXT,actual_status TEXT,note TEXT,detected_at TEXT);
CREATE TABLE resource_incidents(id INTEGER PRIMARY KEY,resource_type TEXT,resource_key TEXT,display_name TEXT,incident_type TEXT,incident_state TEXT,baseline_state TEXT,expected_status TEXT,abnormal_status TEXT,opened_observation_id INTEGER,last_abnormal_observation_id INTEGER,recovered_observation_id INTEGER,opened_at TEXT,last_abnormal_at TEXT,recovered_at TEXT,occurrence_count INTEGER,note TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE hardware_observations(id INTEGER PRIMARY KEY,observed_at TEXT,host TEXT,recorded_at TEXT);
CREATE TABLE hardware_events(id INTEGER PRIMARY KEY,observation_id INTEGER,serial TEXT,role TEXT,model TEXT,outcome TEXT,severity TEXT,temperature_c REAL,changes_json TEXT,observed_at TEXT,recorded_at TEXT);
CREATE TABLE hardware_incidents(id INTEGER PRIMARY KEY,serial TEXT,role TEXT,model TEXT,incident_type TEXT,severity TEXT,incident_state TEXT,opened_event_id INTEGER,last_event_id INTEGER,opened_observation_id INTEGER,last_abnormal_observation_id INTEGER,recovered_observation_id INTEGER,opened_at TEXT,last_abnormal_at TEXT,recovered_at TEXT,occurrence_count INTEGER,opening_changes_json TEXT,latest_changes_json TEXT,note TEXT,created_at TEXT,updated_at TEXT);
"""

class ApiV11Timeline(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(":memory:"); self.db.row_factory=sqlite3.Row; self.db.executescript(SCHEMA)
  obs=[(1,"backup_domain","2026-09-29T01:00:00Z","ms01",1,"2026-09-29T01:00:01Z",'{"secret":"DO-NOT-EXPOSE"}'),(2,"backup_domain","2026-09-29T02:00:00Z","ms01",1,"2026-09-29T02:00:01Z",'{}'),(3,"backup_domain","2026-09-29T03:00:00Z","ms01",1,"2026-09-29T03:00:01Z",'{}')]
  self.db.executemany("INSERT INTO observations VALUES(?,?,?,?,?,?,?)",obs)
  events=[(10,1,"backup_phone","olivia","STATUS-CHANGED","VERIFIED",'[{"field":"age","actual":170,"expected":"<=168"}]',"2026-09-29T01:00:00Z","2026-09-29T01:00:01Z"),(11,2,"backup_phone","olivia","STATUS-CHANGED","VERIFIED",'[{"field":"age","actual":171,"expected":"<=168"}]',"2026-09-29T02:00:00Z","2026-09-29T02:00:01Z")]
  self.db.executemany("INSERT INTO backup_events VALUES(?,?,?,?,?,?,?,?,?)",events)
  self.db.execute("INSERT INTO backup_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(1,'backup_phone','olivia','Olivia phone','STATUS-CHANGED','RECOVERED','VERIFIED',10,11,1,2,3,'2026-09-29T01:00:00Z','2026-09-29T02:00:00Z','2026-09-29T03:00:00Z',2,'[{"field":"age","actual":170,"expected":"<=168"}]','[{"field":"age","actual":171,"expected":"<=168"}]',None,'2026-09-29T01:00:00Z','2026-09-29T03:00:00Z'))
  self.db.execute("INSERT INTO observations VALUES(20,'pve_cluster_resources','2026-09-29T04:00:00Z','ms01',1,'2026-09-29T04:00:01Z','{}')")
  self.db.execute("INSERT INTO resource_events VALUES(7,20,'STATUS-CHANGED','qemu','100','HA','VERIFIED','running','stopped',NULL,'2026-09-29T04:00:00Z')")
  self.db.execute("INSERT INTO resource_incidents VALUES(2,'qemu','100','HA','STATUS-CHANGED','OPEN','VERIFIED','running','stopped',20,20,NULL,'2026-09-29T04:00:00Z','2026-09-29T04:00:00Z',NULL,1,NULL,'2026-09-29T04:00:00Z','2026-09-29T04:00:00Z')")
  self.db.execute("INSERT INTO hardware_observations VALUES(30,'2026-09-29T05:00:00Z','ms01','2026-09-29T05:00:01Z')")
  self.db.execute("INSERT INTO hardware_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",(40,30,'SER123','data-disk','X24','OPENED','HOT',58.0,'[{"field":"temperature_c","actual":58.0,"expected":"<55"}]','2026-09-29T05:00:00Z','2026-09-29T05:00:01Z'))
  self.db.execute("INSERT INTO hardware_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(3,'SER123','data-disk','X24','HARDWARE_TEMP_HOT','HOT','OPEN',40,40,30,30,None,'2026-09-29T05:00:00Z','2026-09-29T05:00:00Z',None,1,'[{"field":"temperature_c","actual":58.0,"expected":"<55"}]','[{"field":"temperature_c","actual":58.0,"expected":"<55"}]',None,'2026-09-29T05:00:00Z','2026-09-29T05:00:00Z'))
  self.db.commit()
 def tearDown(self): self.db.close()

 def test_direct_timeline_has_authoritative_lifecycle(self):
  t=incident_timeline(self.db,"BACKUP:1")
  self.assertEqual(t["provenance"]["linkage_mode"],"DIRECT_EVENT_IDS")
  self.assertEqual([x["kind"] for x in t["items"]],["INCIDENT_OPENED","LAST_ABNORMAL","INCIDENT_RECOVERED"])
  self.assertEqual(t["items"][0]["event_id"],"BACKUP:10")
  self.assertEqual(t["items"][-1]["observation_id"],"BACKUP:3")
 def test_bundle_is_sanitized_and_recovery_can_be_observation_only(self):
  b=incident_evidence_bundle(self.db,"BACKUP:1")
  self.assertEqual(b["opening_evidence"]["event"]["id"],"event:BACKUP:10")
  self.assertEqual(b["recovery_evidence"]["observation"]["id"],"observation:BACKUP:3")
  self.assertIsNone(b["recovery_evidence"]["event"])
  self.assertNotIn("DO-NOT-EXPOSE",str(b)); self.assertNotIn("payload_json",str(b))

 def test_pve_uses_explicit_legacy_provenance(self):
  t=incident_timeline(self.db,"PVE:2")
  self.assertEqual(t["provenance"]["linkage_mode"],"LEGACY_RESOURCE_TIME_CORRELATION")
  self.assertFalse(t["provenance"]["direct_event_linkage"])
  self.assertEqual(t["items"][0]["event_id"],"PVE:7")
  self.assertEqual(t["items"][0]["changes"][0]["actual"],"stopped")

 def test_hardware_direct_linkage_without_resource_key_column(self):
  t=incident_timeline(self.db,"HARDWARE:3")
  self.assertEqual(t["provenance"]["linkage_mode"],"DIRECT_EVENT_IDS")
  self.assertEqual(t["resource_key"],"SER123")
  self.assertEqual(t["items"][0]["event_id"],"HARDWARE:40")
  b=incident_evidence_bundle(self.db,"HARDWARE:3")
  self.assertEqual(b["opening_evidence"]["observation"]["id"],"observation:HARDWARE:30")

 def test_nested_routes_and_bad_ids(self):
  code,p=route(self.db,"/v1/incidents/BACKUP:1/timeline",{})
  self.assertEqual(code,200); self.assertEqual(p["data"]["incident_id"],"BACKUP:1")
  code,p=route(self.db,"/v1/incidents/BACKUP:1/evidence-bundle",{})
  self.assertEqual(code,200); self.assertEqual(p["data"]["authority"],"DERIVED")
  code,p=route(self.db,"/v1/incidents/1/timeline",{})
  self.assertEqual(code,400); self.assertEqual(p["error"]["code"],"INVALID_ID")
  code,p=route(self.db,"/v1/incidents/BACKUP:1/evidence-bundle",{"limit":"bad"})
  self.assertEqual(code,400); self.assertEqual(p["error"]["code"],"INVALID_LIMIT")
  code,p=route(self.db,"/v1/incidents/BACKUP:1/evidence-bundle",{"limit":"51"})
  self.assertEqual(code,400); self.assertEqual(p["error"]["code"],"INVALID_LIMIT")

if __name__=="__main__": unittest.main()
