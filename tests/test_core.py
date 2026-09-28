import os, tempfile, unittest
from pathlib import Path
from rackmarshal.core.config import load_config, require, ConfigError
from rackmarshal.cli import validate
class CoreTests(unittest.TestCase):
 def test_config_parse(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"c"; p.write_text("STATE_DB=/tmp/state.db\nSITE_NAME=test\n")
   self.assertEqual(load_config(p)["SITE_NAME"],"test")
   self.assertEqual(validate(p),[])
 def test_required(self):
  with self.assertRaises(ConfigError): require({},"STATE_DB")
 def test_bad_domain(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"c"; p.write_text("STATE_DB=/tmp/x\nENABLED_DOMAINS=nope\n")
   self.assertTrue(validate(p))
if __name__=="__main__": unittest.main()
