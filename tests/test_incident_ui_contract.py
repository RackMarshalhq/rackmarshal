import unittest
from pathlib import Path

class IncidentUiContractFreeze(unittest.TestCase):
 def test_contract_is_frozen_and_read_only(self):
  text=Path('contracts/ui-v1.1/INCIDENT_SUMMARY_PAGE.md').read_text()
  self.assertIn('FROZEN IMPLEMENTATION CONTRACT',text)
  self.assertIn('MUST NOT use an AI model',text)
  self.assertIn('no write/acknowledge/close/restart controls',text)
 def test_contract_requires_open_and_recovered_truth(self):
  text=Path('contracts/ui-v1.1/INCIDENT_SUMMARY_PAGE.md').read_text()
  self.assertIn('No recovery is recorded',text)
  self.assertIn('recorded recovery time',text)
  self.assertIn('PVE legacy incident',text)

if __name__=='__main__': unittest.main()
