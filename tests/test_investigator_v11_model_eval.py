import unittest
from rackmarshal.agent.model_eval import score_case

class InvestigatorV11ModelEval(unittest.TestCase):
 def fake(self,text,tools):
  out=[{"type":"mcp_call","name":t} for t in tools]
  out.append({"type":"message","content":[{"type":"output_text","text":text}]})
  return {"output":out}
 def test_recovery_case_requires_typed_evidence(self):
  case={"required_tools":["get_incident_timeline"],"evidence_id_required":True,"must_contain":["BACKUP:33"]}
  r=score_case(case,self.fake("BACKUP:33 recovered; evidence observation:BACKUP:10356.",["get_incident_timeline"]))
  self.assertTrue(r["pass"],r)
 def test_missing_required_tool_fails(self):
  case={"required_tools":["get_incident_evidence_bundle"]}
  r=score_case(case,self.fake("answer",[]))
  self.assertFalse(r["pass"]); self.assertTrue(any("missing tools" in x for x in r["failures"]))
 def test_cause_boundary_requires_uncertainty(self):
  case={"required_tools":[],"uncertainty_required":True}
  self.assertFalse(score_case(case,self.fake("The root cause was X.",[]))["pass"])
  self.assertTrue(score_case(case,self.fake("RackMarshal does not establish the cause.",[]))["pass"])
 def test_separation_requirement(self):
  case={"required_tools":[],"separation_required":True}
  self.assertTrue(score_case(case,self.fake("Recorded facts: X. Advisory interpretation: Y.",[]))["pass"])
  self.assertFalse(score_case(case,self.fake("X happened.",[]))["pass"])

if __name__=="__main__": unittest.main()
