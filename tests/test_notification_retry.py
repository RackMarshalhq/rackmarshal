import json,sqlite3,unittest
from unittest.mock import patch
from rackmarshal.notifications.delivery import deliver_one

class NotificationRetryTests(unittest.TestCase):
 def test_recovered_row_retries_dismiss_and_marks_sent(self):
  c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
  c.executescript('''create table incident_notifications(id integer primary key,source_domain text,incident_id integer,notification_type text,delivery_state text,attempt_count integer default 0,last_attempt_at text,updated_at text,packet_json text,explanation_json text,delivered_at text,last_error text);''')
  opened={'schema_version':1,'builder':'incident_notification_packet','source_domain':'PVE','incident_id':1,'notification_type':'OPENED','incident':{'display_name':'Fictional VM','incident_type':'STATUS-CHANGED'}}
  recovered={'schema_version':1,'builder':'incident_notification_packet','source_domain':'PVE','incident_id':1,'notification_type':'RECOVERED','incident':{'display_name':'Fictional VM','incident_type':'STATUS-CHANGED','expected_status':'running','abnormal_status':'stopped','opened_at':'2026-01-01T00:00:00Z','recovered_at':'2026-01-01T00:05:00Z'}}
  c.execute("insert into incident_notifications values(10,'PVE',1,'OPENED','SENT',1,null,null,?,null,'2026-01-01',null)",(json.dumps(opened),))
  c.execute("insert into incident_notifications values(11,'PVE',1,'RECOVERED','PENDING',0,null,null,?,null,null,null)",(json.dumps(recovered),)); c.commit()
  row=c.execute('select * from incident_notifications where id=11').fetchone()
  with patch('rackmarshal.notifications.delivery.dismiss_ha',side_effect=RuntimeError('fictional outage')):
   self.assertEqual(deliver_one(c,row,'http://fixture','token','unused','test')['result'],'FAILED')
  row=c.execute('select * from incident_notifications where id=11').fetchone(); self.assertEqual(row['delivery_state'],'FAILED'); self.assertEqual(row['attempt_count'],1)
  with patch('rackmarshal.notifications.delivery.dismiss_ha',return_value=None) as dismiss, patch('rackmarshal.notifications.delivery.send_ha') as create:
   self.assertEqual(deliver_one(c,row,'http://fixture','token','unused','test')['result'],'SENT')
   dismiss.assert_called_once_with('http://fixture','token','test_pve_1_opened_10')
   create.assert_not_called()
  row=c.execute('select * from incident_notifications where id=11').fetchone(); self.assertEqual(row['delivery_state'],'SENT'); self.assertEqual(row['attempt_count'],2); self.assertIsNone(row['last_error']); self.assertIsNotNone(row['delivered_at'])

 def test_recovery_without_sent_open_notification_is_a_noop_clear(self):
  c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
  c.executescript('''create table incident_notifications(id integer primary key,source_domain text,incident_id integer,notification_type text,delivery_state text,attempt_count integer default 0,last_attempt_at text,updated_at text,packet_json text,explanation_json text,delivered_at text,last_error text);''')
  p={'schema_version':1,'builder':'incident_notification_packet','source_domain':'PVE','incident_id':2,'notification_type':'RECOVERED','incident':{'display_name':'Never Sent','incident_type':'STATUS-CHANGED','recovered_at':'2026-01-01T00:05:00Z'}}
  c.execute("insert into incident_notifications values(1,'PVE',2,'RECOVERED','PENDING',0,null,null,?,null,null,null)",(json.dumps(p),)); c.commit(); row=c.execute('select * from incident_notifications').fetchone()
  with patch('rackmarshal.notifications.delivery.dismiss_ha') as dismiss, patch('rackmarshal.notifications.delivery.send_ha') as create:
   self.assertEqual(deliver_one(c,row,'http://fixture','token','unused','test')['result'],'SENT')
   dismiss.assert_not_called(); create.assert_not_called()
