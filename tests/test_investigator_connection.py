import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from rackmarshal.mcp.check import EXPECTED_TOOLS, connection_check, inspect_tools, validate_url

class ConnectionCheckTests(unittest.TestCase):
    def test_endpoints(self):
        for url in ("http://127.0.0.1:8000/mcp", "http://[::1]:8000/mcp", "https://example.invalid/mcp"):
            self.assertEqual(validate_url(url), url)
        for url in ("http://example.invalid/mcp", "https://user:secret@example.invalid/mcp",
                    "https://example.invalid/mcp?token=secret", "file:///mcp",
                    "http://localhost:bad/mcp", "https://example.invalid/other"):
            with self.assertRaises(ValueError): validate_url(url)
    def test_exact_authority_contract(self):
        tools = [NS(name=n, annotations=NS(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
                 for n in EXPECTED_TOOLS]
        self.assertTrue(inspect_tools(tools))
        self.assertFalse(inspect_tools(tools[:-1]))
        tools[0].annotations.destructiveHint = True
        self.assertFalse(inspect_tools(tools))
    def test_failures_are_sanitized(self):
        self.assertEqual(connection_check("https://user:secret@example.invalid/mcp")["reason"], "INVALID_ENDPOINT")
        async def fail(url): raise RuntimeError("private response secret")
        with patch("rackmarshal.mcp.check._check", fail):
            report = connection_check()
        self.assertNotIn("secret", str(report))
        self.assertEqual(report["reason"], "CONNECTION_OR_PROTOCOL_ERROR")
