import unittest
from pathlib import Path

P=Path('contracts/mcp-v1.1/INCIDENT_INVESTIGATION_TOOLS.md')

class McpV11ContractFreeze(unittest.TestCase):
 def test_contract_is_frozen(self):
  text=P.read_text(); self.assertIn('FROZEN IMPLEMENTATION CONTRACT',text)
 def test_exact_two_new_tool_names_are_frozen(self):
  text=P.read_text()
  self.assertIn('`get_incident_timeline`',text)
  self.assertIn('`get_incident_evidence_bundle`',text)
  self.assertIn('exactly 11 tools',text)
 def test_authority_boundary_is_frozen(self):
  text=P.read_text()
  self.assertIn('readOnlyHint=true',text)
  self.assertIn('destructiveHint=false',text)
  self.assertIn('openWorldHint=false',text)
  self.assertIn('MUST NOT infer cause, severity, or recovery',text)
 def test_bundle_limit_and_sanitization_are_frozen(self):
  text=P.read_text()
  self.assertIn('range 1–50',text)
  self.assertIn('payload_json',text)
  self.assertIn('Invalid canonical IDs MUST become tool errors',text)

if __name__=='__main__': unittest.main()
