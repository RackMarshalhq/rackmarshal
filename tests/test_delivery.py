import atexit
import os, sqlite3, tempfile, unittest
from pathlib import Path
_td=tempfile.TemporaryDirectory(); atexit.register(_td.cleanup); _c=Path(_td.name)/'c'; _c.write_text(f'STATE_DB={_td.name}/x.db\nLOCAL_AI_ENABLED=false\n'); os.environ['RACKMARSHAL_CONFIG']=str(_c)
from rackmarshal.notifications.delivery import deliver_one
class DeliveryTests(unittest.TestCase):
 def test_failed_delivery_is_persisted_and_retryable(self):
  con=sqlite3.connect(':memory:'); con.row_factory=sqlite3.Row
  con.execute('create table incident_notifications(id integer primary key,source_domain text,incident_id integer,notification_type text,delivery_state text,attempt_count integer default 0,last_attempt_at text,updated_at text,packet_json text,explanation_json text,delivered_at text,last_error text)')
  packet='{"schema_version":1,"builder":"incident_notification_packet","source_domain":"PVE","incident_id":7,"notification_type":"OPENED","incident":{"display_name":"fictional-vm","incident_type":"STATUS","expected_status":"running","actual_status":"stopped"}}'
  con.execute("insert into incident_notifications(id,source_domain,incident_id,notification_type,delivery_state,packet_json) values(1,'PVE',7,'OPENED','PENDING',?)",(packet,)); con.commit()
  row=con.execute('select * from incident_notifications where id=1').fetchone()
  result=deliver_one(con,row,'http://127.0.0.1:1','invalid','unused','test')
  self.assertEqual(result['result'],'FAILED')
  state=con.execute('select delivery_state,attempt_count,last_error from incident_notifications where id=1').fetchone()
  self.assertEqual(state[0],'FAILED'); self.assertEqual(state[1],1); self.assertTrue(state[2])
  con.close()
