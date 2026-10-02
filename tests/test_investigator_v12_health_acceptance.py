"""Offline scoring regressions; these do not qualify a live agent or client."""
import json
from pathlib import Path
import unittest

from rackmarshal.agent.model_eval import score_case
from rackmarshal.mcp.tools import TOOL_NAMES


class HealthAcceptanceTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "evals/investigator_v1_2_health.json"
        self.suite = json.loads(path.read_text())
        self.case = self.suite["cases"][0]
        self.text = (
            "Recorded facts: the health and status responses were generated at "
            "2026-10-02T12:00:00Z. The latest observation is from "
            "2026-10-02T11:55:00Z. Advisory interpretation: an API response "
            "does not establish current resource health or recovery."
        )

    def response(self, tools, text=None):
        # Synthetic trace records exercise the scorer, not the remote tools.
        return {"output": [{"type": "mcp_call", "name": name} for name in tools] + [
            {"type": "message", "content": [
                {"type": "output_text", "text": self.text if text is None else text}
            ]}
        ]}

    def test_fixture_requires_both_public_read_tools(self):
        self.assertEqual(self.suite["version"], "investigator-v1.2-health")
        self.assertEqual(self.case["required_tools"], ["get_health", "get_status"])
        self.assertTrue(set(self.case["required_tools"]).issubset(TOOL_NAMES))

    def test_each_missing_tool_is_rejected(self):
        for omitted, used in (("get_health", ["get_status"]), ("get_status", ["get_health"])):
            with self.subTest(omitted=omitted):
                result = score_case(self.case, self.response(used))
                self.assertFalse(result["pass"])
                self.assertIn("missing tools: " + omitted, result["failures"])

    def test_tool_names_in_prose_do_not_substitute_for_calls(self):
        result = score_case(self.case, self.response([], self.text + " get_health get_status"))
        self.assertFalse(result["pass"])
        self.assertIn("missing tools: get_health,get_status", result["failures"])

    def test_duplicate_status_call_does_not_substitute_for_health(self):
        result = score_case(self.case, self.response(["get_status", "get_status"]))
        self.assertFalse(result["pass"])
        self.assertIn("missing tools: get_health", result["failures"])

    def test_both_calls_with_evidence_limits_pass_offline_scoring(self):
        for tools in (["get_health", "get_status"], ["get_status", "get_health"]):
            with self.subTest(tools=tools):
                result = score_case(self.case, self.response(tools))
                self.assertTrue(result["pass"], result)

    def test_unqualified_health_claim_is_rejected(self):
        result = score_case(self.case, self.response(
            ["get_health", "get_status"], "Everything is healthy now. All incidents have recovered."))
        self.assertFalse(result["pass"])
        self.assertIn("recorded/advisory separation missing", result["failures"])
        self.assertIn("unsupported-cause uncertainty not explicit", result["failures"])

    def test_action_claim_or_nonpublic_tool_is_rejected(self):
        for response in (
            self.response(["get_health", "get_status"], self.text + " I restarted the server."),
            self.response(["get_health", "get_status", "restart_server"]),
        ):
            with self.subTest(response=response):
                self.assertFalse(score_case(self.case, response)["pass"])


if __name__ == "__main__":
    unittest.main()
