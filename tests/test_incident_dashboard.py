import unittest
from rackmarshal.ui.dashboard import dashboard_data, render_incident_index
from tests.test_api_v11_timeline import ApiV11Timeline

class IncidentDashboard(unittest.TestCase):
 def setUp(self):
  self.fx=ApiV11Timeline(); self.fx.setUp(); self.db=self.fx.db
 def tearDown(self):
  self.fx.tearDown()
 def test_data_separates_open_and_recovered(self):
  data=dashboard_data(self.db)
  self.assertTrue(all(x["state"]=="OPEN" for x in data["open_incidents"]))
  self.assertTrue(all(x["state"]=="RECOVERED" for x in data["recent_recoveries"]))
  times=[x["recovered_at"] for x in data["recent_recoveries"]]
  self.assertEqual(times,sorted(times,reverse=True))
 def test_page_links_to_detail_pages(self):
  page=render_incident_index(self.db)
  self.assertIn("Open incidents",page)
  self.assertIn("Recent recoveries",page)
  self.assertIn("/incidents/BACKUP:1",page)
  self.assertIn("deterministic and read-only",page)
  self.assertNotIn("payload_json",page)
 def test_dashboard_escapes_resource_text(self):
  self.db.execute("UPDATE backup_incidents SET display_name=? WHERE id=1",("<b>unsafe</b>",)); self.db.commit()
  page=render_incident_index(self.db)
  self.assertNotIn("<b>unsafe</b>",page)
  self.assertIn("&lt;b&gt;unsafe&lt;/b&gt;",page)

if __name__=="__main__": unittest.main()
