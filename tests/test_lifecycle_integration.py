"""Synthetic CLI boundaries and real isolated semantic execution; no systemd writes."""
import importlib.util
import json
import io
from types import SimpleNamespace
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import venv
from rackmarshal.maintenance import lifecycle_semantics as P
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lifecycle_cli',ROOT/'scripts/lifecycle.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)

class IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
 def test_cli_refuses_unisolated_invocation_before_mutation(self):
  result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/lifecycle.py'),'upgrade','--previous-wheel','/nonexistent'],capture_output=True,text=True)
  self.assertEqual(result.returncode,1);self.assertIn('Linux root python3 -I -B -S required',result.stderr)
 def test_final_activation_paths(self):
  target=self.root/'staging';venv.EnvBuilder(with_pip=False).create(target)
  C.finalize_venv(target)
  for name in ('activate','activate.csh','activate.fish','Activate.ps1'):
   self.assertNotIn(str(target),(target/'bin'/name).read_text())
  self.assertNotIn(str(target),(target/'pyvenv.cfg').read_text())
  self.assertIn(str(C.ACTIVE),(target/'bin/activate').read_text())
 def test_manifest_requires_source_binding_and_exact_file_set(self):
  file=self.root/'install-manifest.json'
  with patch.object(C,'ROOT',self.root),patch.object(C.B,'BUNDLE_FILES',{'payload'}),patch.object(C.B,'trusted_read',lambda p:p.read_bytes()):
   (self.root/'payload').write_bytes(b'payload')
   value={'version':C.B.VERSION,'files':{'payload':C.B.digest(b'payload')}}
   file.write_text(json.dumps(value))
   with self.assertRaisesRegex(ValueError,'source commit absent'):C.validate_bundle()
   value['source_commit']='a'*40;file.write_text(json.dumps(value));self.assertEqual(C.validate_bundle(),value)
   (self.root/'payload').write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'bundle differs'):C.validate_bundle()
 def test_readiness_requires_service_identity_and_valid_bodies(self):
  state={'ActiveState':'active','SubState':'running','MainPID':'42','NRestarts':'0','InvocationID':'known'}
  class Response(io.BytesIO):status=200
  for scenario in ('good','foreign-listener','restarted','bad-body','changed-pid'):
   with self.subTest(scenario=scenario):
    before=dict(state);observed=dict(state)
    if scenario=='restarted':observed['NRestarts']='1'
    calls=[dict(observed),dict(observed)]
    if scenario=='changed-pid':calls[-1]['MainPID']='43'
    runtime=SimpleNamespace(fields=lambda name:calls.pop(0))
    body={'status':'BAD' if scenario=='bad-body' else 'OK'}
    responses=[Response(json.dumps(body).encode()),Response(json.dumps({'data':{'status':'OK','database_readable':True}}).encode())]
    opener=SimpleNamespace(open=lambda *a,**kw:responses.pop(0))
    error=ValueError('foreign listener') if scenario=='foreign-listener' else None
    with patch('urllib.request.build_opener',return_value=opener),patch.object(C,'validate_listener',side_effect=error),patch('time.monotonic',side_effect=[0,16]):
     if scenario=='good':C.status_ready(runtime,'rackmarshal-status.service',123,before)
     else:
      with self.assertRaises(ValueError):C.status_ready(runtime,'rackmarshal-status.service',123,before)
 def test_listener_requires_socket_owned_by_main_pid(self):
  tcp='header\n0: 0100007F:2396 00000000:0000 0A 0 0 0 0 0 999\n'
  def read(path):
   if str(path)=='/proc/net/tcp':return tcp
   if str(path)=='/proc/net/tcp6':return 'header\n'
   return 'Uid: 123 123 123 123\n'
  with patch.object(Path,'read_text',read),patch.object(Path,'iterdir',return_value=iter([Path('/proc/42/fd/1')])),patch.object(C.os,'readlink',return_value='socket:[1000]'):
   with self.assertRaisesRegex(ValueError,'not owned'):C.validate_listener(42,123)
 def test_real_semantic_proof_uses_only_synthetic_database(self):
  target=self.root/'venv';venv.EnvBuilder(with_pip=False).create(target)
  site=next(target.glob('lib/python*/site-packages'))
  shutil.copytree(ROOT/'rackmarshal',site/'rackmarshal',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
  work=self.root/'proof';work.mkdir()
  result=P.proof(target/'bin/python',work)
  self.assertEqual(result['result'],'FIXTURE_ASSERTIONS_PASS')
  from rackmarshal.maintenance import lifecycle as L
  payload={str(p.relative_to(ROOT)):p.read_bytes() for p in (ROOT/'rackmarshal/db/migrations').glob('*.sql')}
  C.schema_matches(L,work/'fixture.db',payload)
  import sqlite3
  connection=sqlite3.connect(work/'fixture.db')
  try:connection.execute('CREATE TABLE unexpected (value TEXT)');connection.commit()
  finally:connection.close()
  with self.assertRaisesRegex(ValueError,'live schema differs'):C.schema_matches(L,work/'fixture.db',payload)
  self.assertEqual(len(result['commands']),55);self.assertEqual(result['cycle_count'],9)
  self.assertEqual(result['parser']['parser_cases'],15)
  self.assertEqual(sum(x['returncode']!=0 for x in result['commands']),7)
  with self.assertRaisesRegex(RuntimeError,'fixture must be new'):P.proof(target/'bin/python',work)

if __name__=='__main__':unittest.main()
