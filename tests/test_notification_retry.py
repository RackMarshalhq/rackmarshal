import json,sqlite3,unittest
from unittest.mock import patch
from rackmarshal.notifications.delivery import deliver_one
class NotificationRetryTests(unittest.TestCase):
 def test_failed_row_retries_and_sends_once_delivery_recovers(self):
  c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row; c.executescript("""create table incident_notifications(id integer primary key,source_domain text,incident_id integer,notification_type text,delivery_state text,attempt_count integer default 0,last_attempt_at text,updated_at text,packet_json text,explanation_json text,delivered_at text,last_error text);""")
  packet={'schema_version':1,'builder':'incident_notification_packet','source_domain':'PVE','incident_id':1,'notification_type':'RECOVERED','incident':{'display_name':'Fictional VM','incident_type':'STATUS-CHANGED','expected_status':'running','abnormal_status':'stopped','opened_at':'2026-01-01T00:00:00Z','recovered_at':'2026-01-01T00:05:00Z'}}
  c.execute("insert into incident_notifications values(1,'PVE',1,'RECOVERED','PENDING',0,null,null,?,null,null,null)",(json.dumps(packet),)); c.commit(); row=c.execute('select * from incident_notifications').fetchone()
  with patch('rackmarshal.notifications.delivery.send_ha',side_effect=RuntimeError('fictional outage')): self.assertEqual(deliver_one(c,row,'http://fixture','token','unused','test')['result'],'FAILED')
  row=c.execute('select * from incident_notifications').fetchone(); self.assertEqual(row['delivery_state'],'FAILED'); self.assertEqual(row['attempt_count'],1)
  with patch('rackmarshal.notifications.delivery.send_ha',return_value=None): self.assertEqual(deliver_one(c,row,'http://fixture','token','unused','test')['result'],'SENT')
  row=c.execute('select * from incident_notifications').fetchone(); self.assertEqual(row['delivery_state'],'SENT'); self.assertEqual(row['attempt_count'],2); self.assertIsNone(row['last_error']); self.assertIsNotNone(row['delivered_at'])
