import unittest
from pathlib import Path

class TimelineContractFreeze(unittest.TestCase):
 def test_contract_files_exist_and_are_frozen(self):
  for name in ('INCIDENT_TIMELINE.md','INCIDENT_EVIDENCE_BUNDLE.md'):
   text=Path('contracts/api-v1.1/'+name).read_text()
   self.assertIn('FROZEN IMPLEMENTATION CONTRACT',text)
 def test_timeline_contract_requires_recovery_proof(self):
  text=Path('contracts/api-v1.1/INCIDENT_TIMELINE.md').read_text()
  self.assertIn('recovered_observation_id',text)
  self.assertIn('do not invent event linkage',text.lower())
 def test_bundle_contract_forbids_raw_payloads(self):
  text=Path('contracts/api-v1.1/INCIDENT_EVIDENCE_BUNDLE.md').read_text()
  self.assertIn('MUST NOT expose raw collector',text)
  self.assertIn('payload_json',text)
  self.assertIn('LEGACY_RESOURCE_TIME_CORRELATION',text)

if __name__=='__main__': unittest.main()
