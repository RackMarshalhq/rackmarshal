import json, os, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer

_tmp=tempfile.TemporaryDirectory()
_db=os.path.join(_tmp.name,"state.db")
import sqlite3
con=sqlite3.connect(_db); con.execute("CREATE TABLE observations(id INTEGER PRIMARY KEY)"); con.commit(); con.close()
_conf=os.path.join(_tmp.name,"rackmarshal.conf")
open(_conf,"w").write(f"STATE_DB={_db}\nSTATUS_API_LISTEN_ADDRESS=127.0.0.1\nSTATUS_API_LISTEN_PORT=0\n")
os.environ["RACKMARSHAL_CONFIG"]=_conf
from rackmarshal.api import status

class ApiV1HttpSmoke(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),status.Handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
  cls.base=f'http://127.0.0.1:{cls.server.server_address[1]}'
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=2); _tmp.cleanup()
 def get(self,path):
  try:
   with urllib.request.urlopen(self.base+path,timeout=5) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def test_v1_health_over_http(self):
  code,p=self.get('/v1/health'); self.assertEqual(code,200); self.assertEqual(p['api_version'],'v1'); self.assertTrue(p['data']['database_readable'])
 def test_legacy_health_unchanged(self):
  code,p=self.get('/health'); self.assertEqual(code,200); self.assertEqual(p['status'],'OK'); self.assertNotIn('api_version',p)
 def test_numeric_incident_id_rejected_over_http(self):
  code,p=self.get('/v1/incidents/1'); self.assertEqual(code,400); self.assertEqual(p['error']['code'],'INVALID_ID')
 def test_unknown_endpoint_envelope(self):
  code,p=self.get('/v1/nope'); self.assertEqual(code,404); self.assertEqual(p['error']['code'],'NOT_FOUND')
if __name__=='__main__': unittest.main()
