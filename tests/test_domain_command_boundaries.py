import importlib, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

DOMAINS=('pve','ha','zfs','backup','hardware','mount')

class DomainCommandBoundaryTests(unittest.TestCase):
 def setUp(self):
  self.td=tempfile.TemporaryDirectory(); r=Path(self.td.name); cred=r/'ha.env'; cred.write_text('HA_URL=http://127.0.0.1:9\nHA_TOKEN=fake\n')
  conf=r/'rackmarshal.conf'; conf.write_text(f'STATE_DB={r}/state.db\nINSTALL_ROOT={r}\nHA_CREDENTIAL_FILE={cred}\nSITE_NAME=fixture\nHARDWARE_HOT_THRESHOLD_C=60\nHARDWARE_HOT_REQUIRED_SAMPLES=2\nHARDWARE_URGENT_THRESHOLD_C=75\nHARDWARE_RECOVERY_THRESHOLD_C=55\nHARDWARE_RECOVERY_REQUIRED_SAMPLES=2\n')
  self.old=os.environ.get('RACKMARSHAL_CONFIG'); os.environ['RACKMARSHAL_CONFIG']=str(conf)
 def tearDown(self):
  if self.old is None: os.environ.pop('RACKMARSHAL_CONFIG',None)
  else: os.environ['RACKMARSHAL_CONFIG']=self.old
  for n in list(sys.modules):
   if n.startswith('rackmarshal.domains.'): sys.modules.pop(n,None)
  self.td.cleanup()
 def test_cycle_module_commands_are_flat_argv_and_explainer_is_scalar(self):
  names=('COLLECTOR','WRITER','COMPARATOR','RECORDER','PROCESSOR','PROCESS_HARDWARE_INCIDENTS','ENQUEUER','DELIVERY_WORKER')
  for d in DOMAINS:
   m=importlib.import_module(f'rackmarshal.domains.{d}.cycle')
   for n in names:
    if hasattr(m,n):
     v=getattr(m,n); self.assertIsInstance(v,list,(d,n,v)); self.assertTrue(v,(d,n)); self.assertTrue(all(isinstance(x,str) for x in v),(d,n,v))
   self.assertIsInstance(m.INCIDENT_EXPLAINER,str,d)
 def test_ha_incident_default_comparator_is_executable_argv(self):
  m=importlib.import_module('rackmarshal.domains.ha.incidents')
  self.assertIsInstance(m.COMPARATOR_DEFAULT,list); self.assertTrue(all(isinstance(x,str) for x in m.COMPARATOR_DEFAULT))
  with patch.object(m.subprocess,'run') as run:
   run.return_value.stdout='{}'; m.compare(m.COMPARATOR_DEFAULT,'/tmp/x.db',7)
   argv=run.call_args.args[0]; self.assertEqual(argv[:len(m.COMPARATOR_DEFAULT)],m.COMPARATOR_DEFAULT); self.assertNotIn(None,argv)
 def test_hardware_incident_processor_executes_module_argv_directly(self):
  m=importlib.import_module('rackmarshal.domains.hardware.cycle')
  with patch.object(m.subprocess,'run') as run:
   run.return_value.returncode=0; run.return_value.stdout='{}'; run.return_value.stderr=''
   m.process_hardware_incidents_ledger(); self.assertEqual(run.call_args.args[0],m.PROCESS_HARDWARE_INCIDENTS)
