import inspect, unittest
from rackmarshal.mcp.tools import RackMarshalTools, V10_TOOL_NAMES, TOOL_NAMES, V11_CANDIDATE_TOOL_NAMES

class McpV11Candidate(unittest.TestCase):
 def test_candidate_surface_is_exactly_eleven(self):
  self.assertEqual(len(V10_TOOL_NAMES),9)
  self.assertEqual(len(TOOL_NAMES),11); self.assertEqual(V11_CANDIDATE_TOOL_NAMES,TOOL_NAMES)
  self.assertEqual(V11_CANDIDATE_TOOL_NAMES[-2:],('get_incident_timeline','get_incident_evidence_bundle'))
 def test_new_tool_signatures_are_minimal(self):
  t=inspect.signature(RackMarshalTools.get_incident_timeline)
  b=inspect.signature(RackMarshalTools.get_incident_evidence_bundle)
  self.assertEqual(list(t.parameters),['self','incident_id'])
  self.assertEqual(list(b.parameters),['self','incident_id','limit'])
  self.assertEqual(b.parameters['limit'].annotation,int)
  self.assertEqual(b.parameters['limit'].default,50)
if __name__=='__main__': unittest.main()
