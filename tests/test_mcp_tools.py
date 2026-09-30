import sqlite3, unittest
from rackmarshal.mcp.tools import RackMarshalTools, TOOL_NAMES, ToolError

class McpTools(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:'); self.db.row_factory=sqlite3.Row
  self.db.executescript('''CREATE TABLE resource_incidents(id INTEGER PRIMARY KEY,resource_type TEXT,resource_key TEXT,display_name TEXT,incident_type TEXT,incident_state TEXT,baseline_state TEXT,opened_observation_id INTEGER,last_abnormal_observation_id INTEGER,recovered_observation_id INTEGER,opened_at TEXT,last_abnormal_at TEXT,recovered_at TEXT,occurrence_count INTEGER,opening_changes_json TEXT,latest_changes_json TEXT); CREATE TABLE zfs_incidents AS SELECT * FROM resource_incidents WHERE 0; CREATE TABLE backup_incidents AS SELECT * FROM resource_incidents WHERE 0; CREATE TABLE ha_incidents AS SELECT * FROM resource_incidents WHERE 0;''')
  self.db.execute("INSERT INTO resource_incidents VALUES(1,'qemu','100','VM 100','STOPPED','OPEN','VERIFIED',10,11,NULL,'2026-09-29T01:00:00Z','2026-09-29T02:00:00Z',NULL,2,'{}','{}')"); self.db.commit()
  self.api=RackMarshalTools(self._conn,lambda:{'overall_status':'PROBLEM','open_incident_count':1,'domains':{'PVE':{'status':'PROBLEM','open_incidents':1,'last_observation':'2026-09-29T02:00:00Z'},'BACKUP':{'status':'OK','open_incidents':0,'last_observation':'2026-09-29T02:00:00Z'}},'self_watch':{}})
 def _conn(self):
  # clone fixture because the tool owns/closes each connection
  c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row; self.db.backup(c); return c
 def tearDown(self): self.db.close()
 def test_surface_is_exactly_nine_read_tools(self): self.assertEqual(len(TOOL_NAMES),9); self.assertNotIn('explain_state',TOOL_NAMES)
 def test_list_incidents_is_goal_oriented(self):
  p=self.api.list_incidents(domain='PVE',state='OPEN',limit=5); self.assertEqual(p['data'][0]['id'],'PVE:1')
 def test_get_incident_uses_stable_id(self): self.assertEqual(self.api.get_incident('PVE:1')['data']['resource_key'],'100')
 def test_status_is_deterministic_api_state(self): self.assertEqual(self.api.get_status()['data']['overall_status'],'PROBLEM')
 def test_bad_id_becomes_tool_error(self):
  with self.assertRaises(ToolError): self.api.get_incident('1')
if __name__=='__main__': unittest.main()
