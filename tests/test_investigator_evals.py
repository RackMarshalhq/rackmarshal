import unittest
from rackmarshal.agent.evals import load_cases, validate_case, validate_trace
from rackmarshal.agent.investigator import investigation_plan

class InvestigatorEvalContract(unittest.TestCase):
 def test_eval_suite_has_ten_named_cases(self):
  cases=load_cases(); self.assertEqual(len(cases),10); self.assertEqual(len({c["id"] for c in cases}),10)
 def test_all_eval_cases_reference_verified_tools(self):
  for case in load_cases(): self.assertEqual(validate_case(case),[],case["id"])
 def test_declared_plans_cover_eval_required_tools_where_applicable(self):
  for case in load_cases():
   plan=set(investigation_plan(case["kind"]))
   required=set(case["required_tools"])
   self.assertTrue(required.issubset(plan) or case["kind"] in ("recovery","incident","domain"),case["id"])
 def test_trace_validator_accepts_required_tools(self):
  for case in load_cases():
   result=validate_trace(case,case["required_tools"])
   self.assertTrue(result["pass"],case["id"])
 def test_trace_validator_rejects_shell_like_capability(self):
  case=load_cases()[0]
  result=validate_trace(case,case["required_tools"]+["execute_shell"])
  self.assertFalse(result["pass"]); self.assertIn("execute_shell",result["forbidden_tools"])

if __name__=="__main__": unittest.main()
