import json, unittest
from pathlib import Path
from rackmarshal.mcp.tools import TOOL_NAMES

class InvestigatorV11LiveContract(unittest.TestCase):
 def setUp(self): self.s=json.loads(Path('evals/investigator_v1_1_live.json').read_text())
 def test_suite_is_v11_and_serious(self):
  self.assertEqual(self.s['version'],'investigator-v1.1-live'); self.assertGreaterEqual(len(self.s['cases']),18)
 def test_all_declared_calls_use_public_tools(self):
  allowed=set(TOOL_NAMES)
  for case in self.s['cases']:
   for name,_ in case['calls']: self.assertIn(name,allowed,case['id'])
 def test_suite_covers_new_tools_and_security_failures(self):
  names=[n for c in self.s['cases'] for n,_ in c['calls']]
  self.assertIn('get_incident_timeline',names); self.assertIn('get_incident_evidence_bundle',names)
  self.assertGreaterEqual(sum(bool(c.get('expect_error')) for c in self.s['cases']),3)
 def test_suite_covers_open_recovered_and_legacy(self):
  ids={c['id'] for c in self.s['cases']}
  self.assertTrue({'open_backup_current','recovered_backup','pve_legacy'}.issubset(ids))
if __name__=='__main__': unittest.main()
