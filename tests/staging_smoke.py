#!/usr/bin/env python3
from pathlib import Path
import importlib, os, sqlite3, subprocess, sys, tempfile, tomllib
ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'rackmarshal'
PY=sys.executable
sys.path.insert(0,str(ROOT))

def run(cmd,env=None):
 r=subprocess.run(cmd,text=True,capture_output=True,env=env,timeout=20)
 if r.returncode: raise RuntimeError(f"{cmd}: rc={r.returncode}\n{r.stdout}\n{r.stderr}")
 return r

def main():
 with tempfile.TemporaryDirectory(prefix='rackmarshal-smoke-') as td:
  t=Path(td); db=t/'fresh.db'; kh=t/'known_hosts'; kh.write_text('')
  conf=t/'rackmarshal.conf'
  conf.write_text('\n'.join([
   f'STATE_DB={db}',f'INSTALL_ROOT={ROOT}',f'CONFIG_DIR={t}',f'STATE_DIR={t}',
   f'DOMAINS_DIR={PKG}/domains',f'VENV_PYTHON={PY}','SITE_NAME=smoke-site','PVE_NODE=smoke-node',
   'HARDWARE_HOT_THRESHOLD_C=60','HARDWARE_CRITICAL_THRESHOLD_C=70','HARDWARE_URGENT_THRESHOLD_C=75',
   'HARDWARE_HOT_REQUIRED_SAMPLES=2','HARDWARE_RECOVERY_REQUIRED_SAMPLES=2','HARDWARE_RECOVERY_THRESHOLD_C=55',
   'HARDWARE_SSH_HOST=invalid.example','HARDWARE_SSH_USER=nobody',f'HARDWARE_SSH_KEY={kh}',f'HARDWARE_KNOWN_HOSTS={kh}',
   'HARDWARE_NVME_SERIALS=SMOKE0001','HARDWARE_NVME_SMOKE0001_MODEL=Fake','HARDWARE_NVME_SMOKE0001_ROLE=test',
   'ZFS_SSH_HOST=invalid.example','ZFS_SSH_USER=nobody',f'ZFS_SSH_KEY={kh}',f'ZFS_KNOWN_HOSTS={kh}',
   'STATUS_API_LISTEN_ADDRESS=127.0.0.1','STATUS_API_LISTEN_PORT=19110','LOCAL_AI_ENABLED=false','']))
  env=os.environ.copy();env['PYTHONPATH']=str(ROOT);env['RACKMARSHAL_CONFIG']=str(conf)
  run([PY,'-m','rackmarshal.db.migrations.migrate','--db',str(db),'--apply','--yes'],env)
  con=sqlite3.connect(db); assert con.execute('pragma quick_check').fetchone()[0]=='ok'; assert not con.execute('pragma foreign_key_check').fetchall(); con.close()
  manifests=[]
  for f in sorted((PKG/'domains').glob('*/plugin.toml')):
   d=tomllib.loads(f.read_text()); manifests.extend(d['entrypoints'].values())
  # Import all declared entrypoints under fictional config. Imports must not contact external systems.
  os.environ.update({'RACKMARSHAL_CONFIG':str(conf),'PYTHONPATH':str(ROOT)})
  for m in dict.fromkeys(manifests): importlib.import_module(m)
  # Verify cycle subprocess wiring resolves to package modules, never legacy flat scripts.
  for domain in ['pve','zfs','ha','backup','hardware','mount']:
   m=importlib.import_module(f'rackmarshal.domains.{domain}.cycle')
   for name in ['COLLECTOR','WRITER','COMPARATOR','RECORDER','PROCESSOR','PROCESS_HARDWARE_INCIDENTS','ENQUEUER','DELIVERY_WORKER']:
    if hasattr(m,name):
     v=getattr(m,name); assert isinstance(v,list), (domain,name,v); assert '-m' in v, (domain,name,v); assert not any(str(x).endswith('.py') for x in v), (domain,name,v)
  # Exercise safe CLI construction/parser paths only; no collectors/cycles are executed.
  safe=['rackmarshal.domains.pve.comparator','rackmarshal.domains.pve.events','rackmarshal.domains.pve.incidents','rackmarshal.domains.zfs.comparator','rackmarshal.domains.zfs.events','rackmarshal.domains.zfs.incidents','rackmarshal.domains.ha.comparator','rackmarshal.domains.ha.events','rackmarshal.domains.ha.incidents','rackmarshal.domains.backup.comparator','rackmarshal.domains.backup.events','rackmarshal.domains.backup.incidents','rackmarshal.domains.hardware.incidents','rackmarshal.domains.mount.incidents','rackmarshal.notifications.queue','rackmarshal.notifications.delivery','rackmarshal.incidents.packet']
  for m in safe: run([PY,'-m',m,'--help'],env)
  # Empty notification queue is a real DB operation and must be side-effect free externally.
  q=run([PY,'-m','rackmarshal.notifications.queue','--db',str(db)],env); assert 'incident_notification_enqueuer' in q.stdout
  print(f'PASS fresh_db={db.name} manifests={len(set(manifests))} safe_cli={len(safe)} queue_empty=OK')
if __name__=='__main__': main()
