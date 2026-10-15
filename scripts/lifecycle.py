#!/usr/bin/env python3
"""Private same-schema dev2/dev3 lifecycle. No legacy stable downgrade support."""
import argparse,uuid,hashlib,importlib.util,json,os,pwd,re,sqlite3,stat,subprocess,sys,tempfile,venv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lifecycle_bootstrap',ROOT/'scripts/bootstrap-wheel.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
DEV2='1.2.0rc6.dev2'
DEV2_SHA='137663acf2bd799b606c2a38db15b646d1a4649417f5c5a697a306afcfe725a5'
ACTIVE=Path('/opt/rackmarshal/venv');STORE=Path('/opt/rackmarshal/lifecycle-transactions')
INPUTS=Path('/opt/rackmarshal/lifecycle-inputs');DB=Path('/var/lib/rackmarshal/state.db')
CONFIG=Path('/etc/rackmarshal/rackmarshal.conf');UNIT_DIR=Path('/etc/systemd/system')
MARKER=Path('/opt/rackmarshal/lifecycle-maintenance')


def validate_bundle():
    manifest=json.loads(B.trusted_read(ROOT/'install-manifest.json'),object_pairs_hook=B.unique_object)
    B.require(manifest.get('version')==B.VERSION and set(manifest['files'])==B.BUNDLE_FILES,'wrong complete bundle manifest')
    for name,value in manifest['files'].items():B.require(B.digest(B.trusted_read(ROOT/name))==value,'bundle differs: '+name)
    B.require(re.fullmatch('[0-9a-f]{40}',manifest.get('source_commit') or '') is not None,'bundle source commit absent')
    return manifest


def import_support():
    # Only called after every source module in the bundle has been verified.
    sys.path.insert(0,str(ROOT))
    from rackmarshal.maintenance import lifecycle as L,lifecycle_systemd as S,lifecycle_semantics as P
    return L,S,P


def wheel_inventory(target,wheel,version):
    data=B.trusted_read(wheel);payload=B.validate_wheel(data,'rackmarshal',version)
    B.validate_target(target)
    B.verify_inventory(target,[('rackmarshal',version,payload)])
    site=next(target.glob('lib/python*/site-packages'))
    for name,value in payload.items():
        if not name.endswith('.dist-info/RECORD'):B.require(B.trusted_read(site/name)==value,'wheel payload differs')
    return payload


def installed_version(target):
    sites=list(target.glob('lib/python*/site-packages'));B.require(len(sites)==1,'site layout')
    dist=list(sites[0].glob('rackmarshal-*.dist-info'));B.require(len(dist)==1,'distribution layout')
    return dist[0].name.removeprefix('rackmarshal-').removesuffix('.dist-info')


def protected_files(account):
    config=B.trusted_read(CONFIG).decode();values={}
    for line in config.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        B.require('=' in line,'invalid configuration line');key,value=line.split('=',1);key=key.strip();value=value.strip().strip('\"\'')
        B.require(key not in values,'duplicate configuration key');values[key]=value
    B.require(values.get('STATE_DB')==str(DB) and values.get('VENV_PYTHON',str(ACTIVE/'bin/python'))==str(ACTIVE/'bin/python') and values.get('INSTALL_ROOT','/opt/rackmarshal')=='/opt/rackmarshal','unsupported custom layout')
    B.require(values.get('STATUS_API_LISTEN_ADDRESS')=='127.0.0.1' and values.get('STATUS_API_LISTEN_PORT')=='9110','unsupported status endpoint')
    paths=set()
    for p in CONFIG.parent.rglob('*'):
        B.require(not p.is_symlink(),'linked configuration path')
        if p.is_file():B.trusted_read(p);paths.add(p)
    for key,value in values.items():
        if value and key.endswith(('_KEY','_FILE','_ENV','_KNOWN_HOSTS','_CATALOG')):
            p=Path(value);B.require(p.is_absolute(),'relative credential/catalog path');B.trusted_read(p);paths.add(p)
    for name in B.UNITS:
        if name.startswith('rackmarshal-self-watch'):continue
        p=UNIT_DIR/name;B.require(B.trusted_read(p)==B.trusted_read(ROOT/'packaging/systemd'/name),'unit changes unsupported in private dev2/dev3 chain')
        paths.add(p)
    st=DB.lstat();B.require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode))==(account.pw_uid,account.pw_gid,0o640),'database ownership differs')
    B.require(not DB.parent.is_symlink() and (DB.parent.stat().st_uid,DB.parent.stat().st_gid)==(account.pw_uid,account.pw_gid) and stat.S_IMODE(DB.parent.stat().st_mode)==0o750,'database directory differs')
    return sorted(paths),values


def finalize_venv(target):
    # venv's activation helpers are generated before the final directory exists.
    # Rewrite only this newly created tree; package launchers use installer API.
    old=str(target)
    for name in ('activate','activate.csh','activate.fish','Activate.ps1'):
        path=target/'bin'/name
        if path.exists():
            data=path.read_text();path.write_text(data.replace(old,str(ACTIVE)))
    path=target/'pyvenv.cfg'
    path.write_text(path.read_text().replace(old,str(ACTIVE)))


def normalize_new_tree(target,gid):
    B.validate_target(target)
    for p in (target,*target.rglob('*')):
        if p.is_symlink():continue
        info=p.lstat();B.require(info.st_uid==0,'new tree foreign owner')
        os.chown(p,0,gid);os.chmod(p,0o750 if p.is_dir() or info.st_mode&0o100 else 0o640)


def pristine_schema(payload):
    connection=sqlite3.connect(':memory:')
    try:
        # Exact ledger DDL used by the pinned migration runner, including SQL text.
        connection.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            checksum TEXT,
            note TEXT
        )
        """)
        for name,data in sorted(payload.items()):
            if name.startswith('rackmarshal/db/migrations/') and name.endswith('.sql'):
                connection.executescript(data.decode())
        schema=connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        return B.digest(repr(schema).encode())
    finally:connection.close()


def schema_matches(L,db,payload):
    observed=L.database_snapshot(db)
    expected={Path(name).stem:B.digest(data) for name,data in payload.items() if name.startswith('rackmarshal/db/migrations/') and name.endswith('.sql')}
    B.require(dict(observed['ledger'])==expected,'migration ledger is not exactly supported')
    B.require(observed['schema_sha256']==pristine_schema(payload),'live schema differs from pinned migrations')
    return observed


def validate_listener(pid,uid):
    rows=[]
    for filename in ('/proc/net/tcp','/proc/net/tcp6'):
        for line in Path(filename).read_text().splitlines()[1:]:
            fields=line.split();address,port=fields[1].split(':')
            if fields[3]=='0A' and int(port,16)==9110:rows.append((filename,address,fields[9]))
    B.require(len(rows)==1 and rows[0][:2]==('/proc/net/tcp','0100007F'),'status listener must be exclusive loopback')
    links=set()
    for path in Path('/proc/'+str(pid)+'/fd').iterdir():
        try:links.add(os.readlink(path))
        except FileNotFoundError:continue
    B.require('socket:['+rows[0][2]+']' in links,'listener not owned by status MainPID')
    fields=dict(line.split(':',1) for line in Path('/proc/'+str(pid)+'/status').read_text().splitlines() if ':' in line)
    B.require(all(int(x)==uid for x in fields['Uid'].split()),'status process UID differs')


def status_ready(runtime,name,uid,before):
    B.require(name=='rackmarshal-status.service','unsupported persistent service')
    import time,urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise RuntimeError('readiness redirect refused')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect());deadline=time.monotonic()+15
    while True:
        try:
            current=runtime.fields(name)
            B.require(current['ActiveState']=='active' and current['SubState']=='running' and int(current['MainPID'])>0,'status not running')
            B.require(current['NRestarts']==before['NRestarts'],'status restarted')
            validate_listener(int(current['MainPID']),uid)
            for endpoint in ('/health','/v1/health'):
                with opener.open('http://127.0.0.1:9110'+endpoint,timeout=2) as response:
                    B.require(response.status==200,'status readiness')
                    body=json.loads(response.read(65537));body=body['data'] if endpoint.startswith('/v1/') else body
                    B.require(body['status']=='OK' and (endpoint=='/health' or body['database_readable'] is True),'status health body differs')
            after=runtime.fields(name)
            B.require(after==current,'status identity changed during readiness')
            validate_listener(int(after['MainPID']),uid)
            return
        except Exception:
            if time.monotonic()>=deadline:raise
            time.sleep(.2)


def semantic(P,python,work):
    work.mkdir(mode=0o700)
    result=P.proof(python,work)
    B.require(result['result']=='FIXTURE_ASSERTIONS_PASS','semantic proof failed')
    return {'receipt':str(work/'receipt.json'),'receipt_sha256':B.digest((work/'receipt.json').read_bytes()),'suite':'zfs-integrity-v1','commands':len(result['commands'])}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['plan','upgrade','rollback','recover'])
    ap.add_argument('--previous-wheel',required=True);ap.add_argument('--transaction');args=ap.parse_args()
    B.require(os.getuid()==os.geteuid()==0 and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and sys.platform=='linux','Linux root python3 -I -B -S required')
    B.require(Path(sys.executable).resolve()==Path('/usr/bin/python3').resolve(),'use trusted system interpreter')
    manifest=validate_bundle();L,S,P=import_support()
    previous=Path(args.previous_wheel).absolute();B.require(B.digest(B.trusted_read(previous))==DEV2_SHA,'only exact corrected dev2 predecessor is supported')
    old_payload=B.validate_wheel(B.trusted_read(previous),'rackmarshal',DEV2)
    new_wheel=ROOT/B.APP_NAME;new_payload=B.validate_wheel(B.trusted_read(new_wheel),'rackmarshal',B.VERSION)
    migrations=lambda p:{n:v for n,v in p.items() if n.startswith('rackmarshal/db/migrations/') and n.endswith('.sql')}
    B.require(migrations(old_payload)==migrations(new_payload),'schema-changing candidate refused')
    account=pwd.getpwnam('rackmarshal');B.require(account.pw_shell=='/usr/sbin/nologin' and account.pw_dir=='/var/lib/rackmarshal','account identity differs')
    protected,config=protected_files(account)
    current=installed_version(ACTIVE) if ACTIVE.exists() else None
    if args.action in ('plan','upgrade'):
        B.require(current==DEV2,'upgrade requires exact dev2; use rollback/recover for an existing transaction')
        wheel_inventory(ACTIVE,previous,DEV2)
    elif ACTIVE.exists():
        B.require(current in (DEV2,B.VERSION),'unsupported installed version')
        wheel_inventory(ACTIVE,previous if current==DEV2 else new_wheel,current)
    expected_old=L.inventory(ACTIVE,0) if ACTIVE.exists() else None
    schema=schema_matches(L,DB,old_payload)
    identity={'source_commit':manifest['source_commit'],'candidate_wheel_sha256':manifest['files'][B.APP_NAME],'previous_version':DEV2,'previous_wheel_sha256':DEV2_SHA,'candidate_version':B.VERSION,'unit_policy':'unchanged-exact-payloads'}
    if args.action=='plan':
        print(json.dumps(dict(identity,result='ARTIFACT_SCHEMA_PLAN_ONLY',schema=schema['schema_sha256'],semantic_proofs='REQUIRED_AT_EXECUTION'),indent=2));return
    for path in (STORE,INPUTS):
        if not path.exists():path.mkdir(mode=0o700);L.fsync_dir(path.parent)
        L.private_dir(path,0);B.require(stat.S_IMODE(path.stat().st_mode)==0o700,'private lifecycle storage required')
    def accept(transaction,journal):
        version=DEV2 if journal.get('rollback') else B.VERSION
        wheel_inventory(ACTIVE,previous if version==DEV2 else new_wheel,version)
        semantic(P,ACTIVE/'bin/python',transaction/('restored-semantic-'+uuid.uuid4().hex if journal.get('rollback') else 'activated-semantic'))
        probe=subprocess.run([str(ACTIVE/'bin/python'),'-I','-B','-c','import rackmarshal.api.v1,rackmarshal.domains.zfs.integrity'],user=account.pw_uid,group=account.pw_gid,extra_groups=[],env={'PATH':'/usr/bin:/bin'},cwd='/',capture_output=True,text=True,timeout=20)
        B.require(probe.returncode==0,'service-account import failed')
        for launcher in ('rackmarshal','rackmarshal-mcp','rackmarshal-investigate','rackmarshal-eval-investigator','rackmarshal-eval-investigator-model'):
            B.require((ACTIVE/'bin'/launcher).read_bytes().startswith(b'#!/opt/rackmarshal/venv/bin/python\n'),'entrypoint has staging path')
    def ready(name,before):status_ready(runtime,name,account.pw_uid,before)
    runtime=S.SystemdRuntime(MARKER,UNIT_DIR,accept,ready)
    engine=L.Lifecycle(ACTIVE,STORE,DB,protected,runtime,owner=0)
    if args.action=='upgrade':
        # Preparation is private and non-activating; engine lock protects mutation.
        stage=B.prepare(ROOT,new_wheel,INPUTS)
        target=stage/'venv';builder=venv.EnvBuilder(with_pip=False,symlinks=True);builder.create(target)
        finalize_venv(target)
        B.install(stage,target,final_python=str(ACTIVE/'bin/python'))
        normalize_new_tree(target,account.pw_gid)
        expected_candidate=L.inventory(target,0)
        evidence={'previous':semantic(P,ACTIVE/'bin/python',stage/'previous-semantic'),
                  'candidate':semantic(P,target/'bin/python',stage/'candidate-semantic')}
        B.require(L.inventory(ACTIVE,0)==expected_old,'predecessor changed during semantic proof')
        B.require(L.inventory(target,0)==expected_candidate,'candidate changed during semantic proof')
        transaction=engine.upgrade(target,identity,expected_old,schema,True,evidence,expected_candidate)
    else:
        B.require(args.transaction is not None,'transaction required')
        transaction=Path(args.transaction).absolute();B.require(transaction.parent==STORE,'foreign transaction')
        journal=json.loads(L.read(transaction/'transaction.json',0));B.require(journal['identity']==identity,'transaction artifacts/source differ')
        old=transaction/'previous' if (transaction/'previous').exists() else ACTIVE
        wheel_inventory(old,previous,DEV2)
        proofdir=Path(tempfile.mkdtemp(prefix='rollback-proof-',dir=INPUTS))
        semantic(P,old/'bin/python',proofdir/'semantic')
        transaction=engine.rollback(transaction,True)
    print('LIFECYCLE_TRANSACTION='+str(transaction));print('LIFECYCLE_RESULT='+json.loads(L.read(transaction/'transaction.json',0))['phase'])

if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as exc:
        print('STOP: '+str(exc),file=sys.stderr);raise SystemExit(1)
