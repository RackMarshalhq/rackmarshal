import unittest
from rackmarshal.agent.openai_client import build_request,extract_text,DEFAULT_MODEL
from rackmarshal.mcp.tools import TOOL_NAMES

class OpenAIInvestigatorClient(unittest.TestCase):
 def test_request_uses_luna_and_exact_tool_allowlist(self):
  body=build_request('What failed overnight?','tunnel_test')
  self.assertEqual(body['model'],DEFAULT_MODEL)
  self.assertEqual(body['model'],'gpt-6-luna')
  self.assertEqual(body['tools'][0]['allowed_tools'],list(TOOL_NAMES))
  self.assertEqual(body['tools'][0]['require_approval'],'never')
 def test_request_uses_tunnel_not_public_server_url(self):
  tool=build_request('status','tunnel_test')['tools'][0]
  self.assertEqual(tool['tunnel_id'],'tunnel_test'); self.assertNotIn('server_url',tool)
 def test_extract_text_reads_message_content(self):
  response={'output':[{'type':'message','content':[{'type':'output_text','text':'Recorded facts'}]}]}
  self.assertEqual(extract_text(response),'Recorded facts')
if __name__=='__main__': unittest.main()
