import unittest
from rackmarshal.api.v1 import incident_summary, route
from rackmarshal.ui.incidents import render_incident_page
from tests.test_api_v11_timeline import ApiV11Timeline

class IncidentSummaryAndUi(unittest.TestCase):
 def setUp(self):
  self.fx=ApiV11Timeline(); self.fx.setUp(); self.db=self.fx.db
 def tearDown(self):
  self.fx.tearDown()
 def test_open_summary_never_invents_recovery_or_cause(self):
  s=incident_summary(self.db,'PVE:2')
  self.assertEqual(s['state'],'OPEN')
  self.assertEqual(s['recovery_statement'],'No recovery is recorded.')
  self.assertIn('does not establish root cause',s['cause_statement'])
  self.assertEqual(s['authority'],'DERIVED')
 def test_recovered_summary_records_recovery(self):
  s=incident_summary(self.db,'BACKUP:1')
  self.assertEqual(s['state'],'RECOVERED')
  self.assertIn('2026-09-29T03:00:00Z',s['recovery_statement'])
  self.assertTrue(s['evidence_refs'])
 def test_summary_route(self):
  code,p=route(self.db,'/v1/incidents/BACKUP:1/summary',{})
  self.assertEqual(code,200); self.assertEqual(p['data']['incident_id'],'BACKUP:1')
 def test_page_renders_timeline_provenance_and_evidence(self):
  page=render_incident_page(self.db,'BACKUP:1')
  self.assertIn('Recorded summary',page)
  self.assertIn('Timeline',page); self.assertIn('DIRECT_EVENT_IDS',page)
  self.assertIn('observation:BACKUP:1',page)
  self.assertNotIn('payload_json',page)
 def test_page_escapes_ledger_text(self):
  self.db.execute("UPDATE backup_incidents SET display_name=? WHERE id=1",('<b>unsafe</b>',)); self.db.commit()
  page=render_incident_page(self.db,'BACKUP:1')
  self.assertNotIn('<b>unsafe</b>',page)
  self.assertIn('&lt;b&gt;unsafe&lt;/b&gt;',page)

if __name__=='__main__': unittest.main()
