import unittest
from rackmarshal.agent.investigator import ALLOWED_TOOLS,SYSTEM_INSTRUCTIONS,investigation_plan
from rackmarshal.mcp.tools import TOOL_NAMES
class InvestigatorContract(unittest.TestCase):
 def test_only_verified_mcp_tools_are_allowed(self): self.assertEqual(ALLOWED_TOOLS,set(TOOL_NAMES))
 def test_no_mutation_language_in_tool_names(self):
  for n in ALLOWED_TOOLS: self.assertFalse(any(v in n for v in ('set_','delete','restart','execute','acknowledge','close_incident')))
 def test_incident_plan_prefers_evidence_bundle(self): self.assertIn('get_incident_evidence_bundle',investigation_plan('incident'))
 def test_recovery_plan_uses_authoritative_history(self): self.assertIn('get_recovery_history',investigation_plan('recovery')); self.assertIn('get_incident_timeline',investigation_plan('recovery'))
 def test_policy_preserves_advisory_boundary(self):
  self.assertIn('ADVISORY',SYSTEM_INSTRUCTIONS); self.assertIn('Never claim an incident recovered',SYSTEM_INSTRUCTIONS)
if __name__=='__main__': unittest.main()
