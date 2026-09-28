import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rackmarshal.notifications.command import build_delivery_command

DOMAINS=("pve","ha","zfs","backup","hardware","mount")

class DeliveryCommandContractTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(); root=Path(self.td.name)
        self.cred=root/'ha.env'; self.cred.write_text('HA_URL=http://127.0.0.1:9999\nHA_TOKEN=fake\n')
        self.conf=root/'rackmarshal.conf'
        self.conf.write_text(f'''STATE_DB={root}/state.db\nSITE_NAME=fixture\nHA_CREDENTIAL_FILE={self.cred}\nHARDWARE_HOT_THRESHOLD_C=60\nHARDWARE_HOT_REQUIRED_SAMPLES=2\nHARDWARE_URGENT_THRESHOLD_C=75\nHARDWARE_RECOVERY_THRESHOLD_C=55\nHARDWARE_RECOVERY_REQUIRED_SAMPLES=2\nMOUNT_DELIVER_TIMEOUT_S=5\n''')
        self.old=os.environ.get('RACKMARSHAL_CONFIG'); os.environ['RACKMARSHAL_CONFIG']=str(self.conf)
    def tearDown(self):
        if self.old is None: os.environ.pop('RACKMARSHAL_CONFIG',None)
        else: os.environ['RACKMARSHAL_CONFIG']=self.old
        for name in list(sys.modules):
            if name.startswith('rackmarshal.domains.') and name.endswith('.cycle'): sys.modules.pop(name,None)
        self.td.cleanup()

    def test_all_six_domains_build_flat_explainer_argv_and_execute_probe(self):
        with tempfile.TemporaryDirectory() as td:
            probe=Path(td)/'probe.py'
            probe.write_text('import json,sys; print(json.dumps(sys.argv[1:]))\n')
            explainer=Path(td)/'rackmarshal-explain'; explainer.write_text('#!/bin/sh\nexit 0\n'); explainer.chmod(0o755)
            for domain in DOMAINS:
                mod=importlib.import_module(f'rackmarshal.domains.{domain}.cycle')
                cmd=build_delivery_command([sys.executable,str(probe)],'/tmp/state.db',self.cred,explainer)
                self.assertTrue(all(isinstance(x,str) for x in cmd),domain)
                idx=cmd.index('--explainer'); self.assertEqual(cmd[idx+1],str(explainer),domain)
                cp=subprocess.run(cmd,text=True,capture_output=True,check=True)
                argv=json.loads(cp.stdout)
                self.assertEqual(argv[argv.index('--explainer')+1],str(explainer),domain)
                self.assertIsInstance(mod.INCIDENT_EXPLAINER,str,domain)

    def test_nested_explainer_argv_is_rejected(self):
        with self.assertRaises(TypeError):
            build_delivery_command(['worker'],'/tmp/db','/tmp/cred',['python','-m','explainer'])
