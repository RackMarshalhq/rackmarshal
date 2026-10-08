import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('gate',ROOT/'scripts/release-candidate-gate.py')
gate=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(gate)

class CandidateGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source='a'*40;self.assets={'wheel':'b'*64}
        self.record={'source_commit':self.source,'artifacts':self.assets,'supported_activation':['local_explicit','private_hosted_explicit'],'gates':{'production_routine_72h':{'status':'PENDING'}}}
        for name in (*gate.REQUIRED,'activation_local_explicit','activation_private_hosted_explicit'):
            receipt={'gate':name,'result':'PASS','source_commit':self.source,'artifacts':self.assets}
            if name.startswith('activation_'):receipt['activation']=name[len('activation_'):]
            if name=='synthetic_72h':
                start=datetime.now(timezone.utc)-timedelta(hours=74)
                samples=[{'sequence':i,'result':'PASS','at':(start+timedelta(seconds=i*300)).isoformat()} for i in range(865)]
                receipt.update(kind='disposable_synthetic',start=samples[0]['at'],finished=samples[-1]['at'],samples=samples)
            self.write(name,receipt)
    def write(self,name,receipt):
        p=self.root/(name+'.json');p.write_text(json.dumps(receipt));self.record['gates'][name]={'status':'PASS','receipt':p.name,'sha256':gate.digest(p)}
    def verify(self,scope='candidate'):return gate.verify(self.record,self.root,self.source,self.assets,scope)
    def test_scoped_candidate_passes_without_production_claim(self):self.assertTrue(self.verify())
    def test_source_artifact_and_receipt_tampering_fail(self):
        for key in ('source_commit','artifacts'):
            old=self.record[key];self.record[key]='wrong'
            with self.assertRaises(ValueError):self.verify()
            self.record[key]=old
        (self.root/'tests.json').write_text('{}')
        with self.assertRaises(ValueError):self.verify()
    def test_pending_missing_and_unsupported_activation_fail(self):
        for status in ('PENDING','FAIL',None):
            self.record['gates']['tests']['status']=status
            with self.assertRaises(ValueError):self.verify()
        self.record['gates']['tests']['status']='PASS';self.record['supported_activation'].append('desktop')
        with self.assertRaises(ValueError):self.verify()
    def test_production_never_substitutes_synthetic(self):
        with self.assertRaises(ValueError):self.verify('stable')
        self.record['gates']['synthetic_72h']['status']='PENDING'
        self.record['gates']['production_routine_72h']=copy.deepcopy(self.record['gates']['tests'])
        with self.assertRaises(ValueError):self.verify()
    def test_elapsed_time_gap_failure_future_and_short_span_fail(self):
        original=gate.read_json(self.root/'synthetic_72h.json')
        for change in ('empty','gap','fail','sequence','short','future','scope'):
            r=copy.deepcopy(original)
            if change=='empty':r['samples']=[]
            if change=='gap':r['samples'][3]['at']=r['samples'][1]['at']
            if change=='fail':r['samples'][5]['result']='FAIL'
            if change=='sequence':r['samples'][5]['sequence']=4
            if change=='short':r['samples']=r['samples'][:5];r['finished']=r['samples'][-1]['at']
            if change=='future':
                for s in r['samples']:s['at']=(gate.instant(s['at'])+timedelta(days=10)).isoformat()
                r['start']=r['samples'][0]['at'];r['finished']=r['samples'][-1]['at']
            if change=='scope':r['kind']='production_routine_use'
            self.write('synthetic_72h',r)
            with self.subTest(change=change),self.assertRaises(ValueError):self.verify()
    def test_duplicate_and_receipt_escape_fail(self):
        p=self.root/'duplicate.json';p.write_text('{"result":"FAIL","result":"PASS"}')
        with self.assertRaises(ValueError):gate.read_json(p)
        self.record['gates']['tests']['receipt']='../elsewhere.json'
        with self.assertRaises(ValueError):self.verify()
    def test_cli_scans_exact_assets_before_checksums_and_rejects_untracked_source(self):
        import shutil,zipfile,tarfile,io
        repo=self.root/'repo';repo.mkdir();(repo/'scripts').mkdir();dist=repo/'dist';dist.mkdir();evidence=repo/'.qualification';evidence.mkdir()
        for name in ('release-candidate-gate.py','release-privacy-gate.py'):shutil.copy2(ROOT/'scripts'/name,repo/'scripts'/name)
        (repo/'pyproject.toml').write_text('[project]\nversion="1.2.0rc4"\n');(repo/'.gitignore').write_text('dist/\n.qualification/\nSHA256SUMS\n')
        for args in (['init','-q'],['add','.'],['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture']):subprocess.run(['git',*args],cwd=repo,check=True,capture_output=True)
        source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
        for name in ('rackmarshal-1.2.0rc4-py3-none-any.whl','rackmarshal-investigator-1.2.0-rc4-local.zip'):
            with zipfile.ZipFile(dist/name,'w') as z:z.writestr('generic.txt','generic')
        for name in ('rackmarshal-1.2.0rc4.tar.gz','rackmarshal-installer-1.2.0-rc4.tar.gz'):
            with tarfile.open(dist/name,'w:gz') as t:
                entry=tarfile.TarInfo('generic.txt');entry.size=7;t.addfile(entry,io.BytesIO(b'generic'))
        def bind():
            assets={p.name:gate.digest(p) for p in dist.iterdir()};record=copy.deepcopy(self.record);record.update(source_commit=source,artifacts=assets)
            for name,g in record['gates'].items():
                if g['status']!='PASS':continue
                receipt=gate.read_json(self.root/g['receipt']);receipt.update(source_commit=source,artifacts=assets);p=evidence/g['receipt'];p.write_text(json.dumps(receipt));g['sha256']=gate.digest(p)
            (evidence/'release.json').write_text(json.dumps(record))
        def run():return subprocess.run([sys.executable,'scripts/release-candidate-gate.py','--source',source,'--record','.qualification/release.json'],cwd=repo,capture_output=True,text=True)
        bind();self.assertEqual(run().returncode,0);self.assertTrue((repo/'SHA256SUMS').exists());(repo/'SHA256SUMS').unlink()
        (repo/'extra.py').write_text('pass')
        self.assertNotEqual(run().returncode,0);self.assertFalse((repo/'SHA256SUMS').exists());(repo/'extra.py').unlink()
        with zipfile.ZipFile(dist/'rackmarshal-1.2.0rc4-py3-none-any.whl','a') as z:z.writestr('secret.txt','ghp_'+'A'*35)
        # Even receipts matching these exact unsafe bytes cannot bypass the scanner.
        bind();self.assertNotEqual(run().returncode,0);self.assertFalse((repo/'SHA256SUMS').exists())
