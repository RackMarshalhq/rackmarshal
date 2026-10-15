#!/usr/bin/env python3
"""Pinned synthetic ZFS proof for exact-validated staged/retained runtimes. No collectors."""
import hashlib, json, os, pathlib, socket, sqlite3, subprocess, sys, tempfile, time, zipfile
from contextlib import closing
P=pathlib.Path
def sha(b): return hashlib.sha256(b).hexdigest()
def require(ok,msg):
    if not ok: raise RuntimeError(msg)
# Runs inside every application subprocess before importing application code.
CHILD=r'''
import sys,os,pathlib,runpy
root=pathlib.Path(sys.argv[1]).resolve(); site=pathlib.Path(sys.argv[2]).resolve(); module=sys.argv[3]; sys.argv=sys.argv[3:]
sys.path.insert(0,str(site))
def inside(path):
    return pathlib.Path(path).resolve().is_relative_to(root)
def audit(event,args):
    if event.startswith(('socket.','subprocess.','os.system','os.exec','os.spawn')): raise RuntimeError('external execution/network forbidden')
    if event in ('os.remove','os.rmdir','os.rename','os.link','os.symlink','os.chmod','os.chown'): raise RuntimeError('mutation forbidden: '+event)
    if event=='open':
        path,mode,flags=args
        if not isinstance(path,(str,bytes,os.PathLike)): raise RuntimeError('unexpected file descriptor')
        if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND) and not inside(path): raise RuntimeError('write outside fixture')
    if event=='os.mkdir' and not inside(args[0]): raise RuntimeError('mkdir outside fixture')
    if event=='sqlite3.connect' and str(args[0]) not in (str(root/'fixture.db'),'file:'+str(root/'fixture.db')+'?mode=ro'): raise RuntimeError('database outside fixture')
sys.addaudithook(audit)
if module=='parser-proof':
    import rackmarshal.domains.zfs.collector as c
    for v,expected in [(None,None),(0,0),('0',0),(11,11),('11',11)]:
        assert c.permanent_error_count(v,'fixture')==expected
    for v in (True,False,-1,0.5,0.0,'0.5','-1','',[],{}):
        try:c.permanent_error_count(v,'fixture')
        except SystemExit:pass
        else:raise AssertionError('invalid parser value accepted')
    print('{"parser_cases":15}')
elif module=='summary-proof':
    import sqlite3,json
    from rackmarshal.api.status import zfs_integrity_summary
    db=sqlite3.connect(os.environ['RACKMARSHAL_STATE_DB']);db.row_factory=sqlite3.Row
    print(json.dumps(zfs_integrity_summary(db)));db.close()
else:runpy.run_module(module,run_name='__main__')
'''
def proof(python,work,site=None):
    sites=list(P(python).parent.parent.glob('lib/python*/site-packages'))
    require(len(sites)==1,'ambiguous site-packages')
    site=P(site) if site is not None else sites[0]
    require(sites==[site],'validated site differs')
    work=P(work).resolve(); db=work/'fixture.db'; config=work/'fixture.conf'
    require(not db.exists() and not config.exists(),'fixture must be new')
    config.write_text(f'STATE_DB={db}\nSITE_NAME=fixture\nSTATUS_API_LISTEN_ADDRESS=127.0.0.1\nSTATUS_API_LISTEN_PORT=9110\nZFS_SSH_HOST=invalid\nZFS_SSH_USER=fixture\nZFS_SSH_KEY=/nonexistent\nZFS_KNOWN_HOSTS=/nonexistent\n')
    env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','RACKMARSHAL_CONFIG':str(config),'RACKMARSHAL_STATE_DB':str(db)}
    report={'proof_suite':'zfs-integrity-v1','result':'IN_PROGRESS','commands':[],'cycles':[],'python':str(python),'fixture_directory':str(work)}
    def save(): (work/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(module,args=(),payload=None,expect_success=True,decode=True):
        command=[str(python),'-I','-B','-S','-c',CHILD,str(work),str(site),module,*args]
        r=subprocess.run(command,input=json.dumps(payload) if payload is not None else None,env=env,cwd=work,text=True,capture_output=True,timeout=20)
        report['commands'].append({'module':module,'args':list(args),'input':payload,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr});save()
        require((r.returncode==0)==expect_success,'unexpected result: '+module)
        return json.loads(r.stdout) if decode and expect_success else r.stdout
    try:
        run('rackmarshal.db.migrations.migrate',['--db',str(db),'--apply','--yes'],decode=False)
        seq=0
        def payload(state,count,guid='1',missing=False):
            nonlocal seq
            seq+=1
            pool={'name':'fixture','pool_guid':guid,'state':state,'error_count':count,'vdevs':[]}
            if missing:del pool['error_count']
            return {'schema_version':1,'collector':'zfs_status','observed_at':f'2026-01-01T00:{seq:02d}:00Z','source':'synthetic','host_key_verified':True,'pool_count':1,'pools':[pool]}
        oid=run('rackmarshal.domains.zfs.observation',payload=payload('ONLINE',0))['observation_id']
        with closing(sqlite3.connect(db)) as c:
            c.execute("INSERT INTO zfs_pool_baseline(pool_name,pool_guid,baseline_state,expected_state,expected_error_count,source_observation_id) VALUES('fixture','1','VERIFIED','ONLINE',0,?)",(oid,))
            c.commit()
        def cycle(state,count,integrity,open_count,recovered=0,guid='1',missing=False):
            p=payload(state,count,guid,missing);oid=run('rackmarshal.domains.zfs.observation',payload=p)['observation_id']
            args=['--database',str(db)]
            comp=run('rackmarshal.domains.zfs.comparator',args+['--observation-id',str(oid)])
            run('rackmarshal.domains.zfs.events',args,comp)
            inc=run('rackmarshal.domains.zfs.incidents',args,comp)
            summary=run('summary-proof')
            with closing(sqlite3.connect(db)) as c:
                rows=c.execute('SELECT incident_state,occurrence_count FROM zfs_incidents').fetchall()
            require(comp['results'][0]['integrity_state']==integrity,'comparator integrity')
            require(summary['state']==integrity,'status integrity')
            require(sum(row[0]=='OPEN' for row in rows)==open_count,'open incident count')
            require(inc['incidents_recovered']==recovered,'recovery count')
            report['cycles'].append({'input':p,'comparison':comp,'incidents':inc,'summary':summary,'ledger_rows':rows});save()
            return rows
        cycle('DEGRADED',0,'CLEAN',1)
        cycle('ONLINE',11,'PROBLEM',1)
        rows=cycle('ONLINE',11,'PROBLEM',1)
        require(rows==[('OPEN',3)],'persistent count must be three')
        cycle('ONLINE',None,'UNKNOWN',1)
        cycle('ONLINE',None,'UNKNOWN',1,missing=True)
        cycle('ONLINE',0,'CLEAN',1,guid='2')
        cycle('DEGRADED',0,'CLEAN',1)
        cycle('ONLINE',0,'CLEAN',0,recovered=1)
        cycle('ONLINE',None,'UNKNOWN',0,missing=True)
        for value in (True,False,-1,0.5,'0',[],{}):
            with closing(sqlite3.connect(db)) as c: before=c.execute('SELECT COUNT(*) FROM zfs_observations').fetchone()[0]
            run('rackmarshal.domains.zfs.observation',payload=payload('ONLINE',value),expect_success=False,decode=False)
            with closing(sqlite3.connect(db)) as c: after=c.execute('SELECT COUNT(*) FROM zfs_observations').fetchone()[0]
            require(after==before,'invalid ingestion changed observations')
        report['parser']=run('parser-proof')
        report.update(result='FIXTURE_ASSERTIONS_PASS',cycle_count=9,invalid_ingestion_cases=7,database_sha256=sha(db.read_bytes()))
    except BaseException as exc:
        report.update(result='FAIL',error=repr(exc));raise
    finally:save()
    return report
