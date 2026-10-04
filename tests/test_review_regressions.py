"""Harmless archive fixtures and actual API timestamp-bound regressions."""
import bz2
import gzip
import io
import lzma
from pathlib import Path
import sqlite3
import tarfile
import unittest
from tests import test_release_privacy as privacy
from tests import test_api_v11_timeline as fixtures
from rackmarshal.api.v1 import _incident_events,incident_summary,query_events,route

class ArchiveReviewTests(unittest.TestCase):
    check=privacy.ReleasePrivacyTests.check
    def test_compressed_nested_renamed_and_tar_variants(self):
        private=('padding '*200+'192.'+'168.99.9'+' padding'*200).encode()
        for suffix,compress in [('bz2',bz2.compress),('xz',lzma.compress),('gz',gzip.compress)]:
            for payload in (private,('ghp_'+'A'*35).encode()):
                for name in ('nested.'+suffix,'renamed.bin'):
                    with self.subTest(suffix=suffix,name=name):self.assertNotEqual(self.check({name:compress(payload)}).returncode,0)
            inner=io.BytesIO()
            with tarfile.open(fileobj=inner,mode='w:'+suffix) as t:
                info=tarfile.TarInfo('data.txt');info.size=len(private);t.addfile(info,io.BytesIO(private))
            self.assertNotEqual(self.check({'nested.tar.'+suffix:inner.getvalue()}).returncode,0)
            self.assertEqual(self.check({'generic.'+suffix:compress(b'generic content')}).returncode,0)
            self.assertNotEqual(self.check({'broken.'+suffix:b'not compressed'}).returncode,0)
    def test_basename_never_exempts_arbitrary_private_text(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('release-privacy-gate.py','publication-gate.sh'):
            for prefix in ('','scripts/','other/nested/'):
                self.assertNotEqual(self.check({prefix+name:'192.'+'168.99.9'}).returncode,0)
            data=(root/'scripts'/name).read_bytes()
            self.assertEqual(self.check({'scripts/'+name:data}).returncode,0)
            self.assertNotEqual(self.check({'scripts/'+name:data+b'\n'+('192.'+'168.99.9').encode()}).returncode,0)
    def test_private_archive_metadata_is_scanned(self):
        import zipfile
        for where in ('comment', 'trailer'):
            inner=io.BytesIO()
            with zipfile.ZipFile(inner,'w') as z:
                z.writestr('generic.txt','generic')
                if where=='comment': z.comment=('asdk_'+'app_'+'a'*32).encode()
            data=inner.getvalue()
            if where=='trailer': data+=('asdk_'+'app_'+'a'*32).encode()
            self.assertNotEqual(self.check({'metadata.zip':data}).returncode,0)
    def test_zip_lzma_without_memory_limit_is_rejected(self):
        import zipfile
        inner=io.BytesIO()
        with zipfile.ZipFile(inner,'w',compression=zipfile.ZIP_LZMA) as z:z.writestr('generic.txt','generic')
        self.assertNotEqual(self.check({'limited.zip':inner.getvalue()}).returncode,0)
    def test_xz_dictionary_memory_and_trailing_data_fail_closed(self):
        large_dictionary=lzma.compress(b'generic', filters=[{'id':lzma.FILTER_LZMA2,'dict_size':128*1024*1024}])
        self.assertNotEqual(self.check({'large-dictionary.xz':large_dictionary}).returncode,0)
        self.assertNotEqual(self.check({'trailing.xz':lzma.compress(b'generic')+b'extra'}).returncode,0)
    def test_total_budget_latches_before_later_reads(self):
        script=(Path(__file__).resolve().parents[1]/'scripts/release-privacy-gate.py').read_text()
        namespace={};exec(compile(script.split('parser=argparse.ArgumentParser')[0],'<scanner>','exec'),namespace)
        namespace['MAX_TOTAL_BYTES']=8
        with self.assertRaises(ValueError): namespace['bounded_read'](io.BytesIO(b'x'*9))
        later=io.BytesIO(b'generic')
        with self.assertRaises(ValueError): namespace['bounded_read'](later)
        self.assertEqual(later.tell(),0)

    def test_depth_and_expansion_limits_fail_closed(self):
        data=b'generic'
        for _ in range(14):data=gzip.compress(data)
        self.assertNotEqual(self.check({'deep.bin':data}).returncode,0)
        self.assertNotEqual(self.check({'large.gz':gzip.compress(b'x'*(64*1024*1024+1))}).returncode,0)

class EvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ApiV11Timeline();self.fixture.setUp();self.db=self.fixture.db;self.addCleanup(self.fixture.tearDown)
    def selected(self,lower,upper,event):
        self.db.execute('UPDATE backup_incidents SET opened_at=?,recovered_at=? WHERE id=1',(lower,upper))
        self.db.execute('UPDATE backup_events SET observed_at=? WHERE id=11',(event,))
        row=dict(self.db.execute('SELECT * FROM backup_incidents WHERE id=1').fetchone());gaps=[]
        return [x['local_id'] for x in _incident_events(self.db,'BACKUP',row,gaps)],gaps
    def test_all_offset_bounds_and_equal_instants(self):
        for lower,upper,event,expected in [('01:00:00Z','03:00:00Z','04:00:00+02:00',True),('03:00:00Z','05:00:00Z','04:00:00+02:00',False),('01:00:00Z','04:00:00+02:00','03:00:00Z',False),('04:00:00+02:00','05:00:00Z','03:00:00Z',True),('02:00:00Z','02:00:00Z','04:00:00+02:00',True)]:
            args=['2026-09-29T'+x for x in (lower,upper,event)]
            with self.subTest(args=args):self.assertEqual(11 in self.selected(*args)[0],expected)
    def test_missing_invalid_naive_events_and_bad_bounds_report_gaps(self):
        for bad in (None,'','bad','2026-09-29T02:00:00'):
            ids,gaps=self.selected('2026-09-29T01:00:00Z','2026-09-29T03:00:00Z',bad)
            self.assertNotIn(11,ids);self.assertTrue(gaps)
            status,body=route(self.db,'/v1/incidents/BACKUP:1/evidence-bundle',{})
            self.assertEqual(status,200);self.assertTrue(body['data']['provenance']['limitations'])
            for lo,hi in [(bad,'2026-09-29T03:00:00Z'),('2026-09-29T01:00:00Z',bad),('2026-09-29T04:00:00Z','2026-09-29T01:00:00Z')]:
                ids,gaps=self.selected(lo,hi,'2026-09-29T02:00:00Z');self.assertEqual(ids,[]);self.assertTrue(gaps)
    def test_order_is_instant_order(self):
        self.db.execute("UPDATE backup_events SET observed_at='2026-09-29T04:00:00+02:00' WHERE id=10")
        self.db.execute("UPDATE backup_events SET observed_at='2026-09-29T02:30:00Z' WHERE id=11")
        self.assertEqual([e['local_id'] for e in query_events(self.db,{'domain':'BACKUP'})],[11,10])
    def test_truthful_recovery_summary_for_legacy_fixture(self):
        self.assertIn('does not establish current resource health',incident_summary(self.db,'BACKUP:1')['recovery_statement'])
        # Legacy fixture deliberately lacks the production CHECK constraint.
        self.db.execute('UPDATE backup_incidents SET recovered_at=NULL WHERE id=1')
        status,body=route(self.db,'/v1/incidents/BACKUP:1/summary',{})
        self.assertEqual(status,200);self.assertIn('ledger is marked RECOVERED',body['data']['recovery_statement'])
        self.db.execute("UPDATE backup_incidents SET incident_state='OPEN',recovered_observation_id=NULL WHERE id=1")
        self.assertEqual(incident_summary(self.db,'BACKUP:1')['recovery_statement'],'No recovery is recorded.')
    def test_production_recovery_constraint_still_rejects_null(self):
        from rackmarshal.domains.mount.incidents import process
        import json
        root=Path(__file__).resolve().parents[1]
        db=sqlite3.connect(':memory:');self.addCleanup(db.close);db.row_factory=sqlite3.Row
        for name in ('000_metadata.sql','007_mount_ledger.sql'):db.executescript((root/'rackmarshal/db/migrations'/name).read_text())
        for index,state in enumerate(('missing','ok')):
            row={'id':'fixture','guest_kind':'host','guest_id':'','mountpoint':'/mnt/fictional','state':state,'optional':False,'severity_missing':'critical'}
            db.execute('INSERT INTO mount_observations(observed_at,source,schema_version,checked_count,ok_count,problem_count,payload_json) VALUES(?,?,?,?,?,?,?)',(f'2026-09-29T0{index+1}:00:00Z','fixture',1,1,int(state=='ok'),int(state=='missing'),json.dumps({'results':[row]})));process(db)
        with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE mount_incidents SET recovered_at=NULL')
