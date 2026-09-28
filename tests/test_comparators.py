import os, tempfile, unittest
from pathlib import Path
_td=tempfile.TemporaryDirectory(); _c=Path(_td.name)/'c'; _c.write_text(f'STATE_DB={_td.name}/x.db\n'); os.environ['RACKMARSHAL_CONFIG']=str(_c)
from rackmarshal.domains.pve.comparator import compare as pve_compare
from rackmarshal.domains.ha.comparator import compare as ha_compare
from rackmarshal.domains.zfs.comparator import pool_match_result
class ComparatorTests(unittest.TestCase):
 def test_pve_match_change_missing_new(self):
  base={('qemu','101'):{'display_name':'alpha','expected_status':'running','baseline_state':'VERIFIED','note':''},('lxc','102'):{'display_name':'beta','expected_status':'running','baseline_state':'VERIFIED','note':''}}
  cur=[{'type':'qemu','vmid':101,'name':'alpha','status':'stopped'},{'type':'storage','storage':'scratch','status':'available'}]
  outcomes={x['resource_key']:x['result'] for x in pve_compare(cur,base)}
  self.assertEqual(outcomes['101'],'STATUS-CHANGED'); self.assertEqual(outcomes['102'],'MISSING'); self.assertEqual(outcomes['scratch'],'NEW')
 def test_ha_match_and_change(self):
  base={'sensor.a':{'resource_key':'sensor.a','resource_type':'entity','display_name':'A','baseline_state':'VERIFIED','expected_status':'on','source_observation_id':1}}
  self.assertEqual(ha_compare(base,{'resources':[{'resource_key':'sensor.a','resource_type':'entity','status':'on'}]})[0]['outcome'],'MATCH')
  self.assertEqual(ha_compare(base,{'resources':[{'resource_key':'sensor.a','resource_type':'entity','status':'off'}]})[0]['outcome'],'STATUS-CHANGED')
 def test_zfs_pool_change(self):
  base={'pool_name':'pool-a','pool_guid':'1','expected_state':'ONLINE','expected_error_count':0,'baseline_state':'VERIFIED'}
  self.assertEqual(pool_match_result(base,{'pool_guid':'1','state':'DEGRADED','error_count':0})['outcome'],'STATUS-CHANGED')
