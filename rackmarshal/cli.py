"""RackMarshal administrative CLI."""
import argparse, importlib, importlib.util, json, os, stat, sys, tomllib, urllib.request
from pathlib import Path
from rackmarshal import __version__
from rackmarshal.core.config import ConfigError, load_config, require

DOMAINS=("pve","zfs","backup","ha","hardware","mount")
ROOT = Path(__file__).resolve().parent

def _enabled(c):
    raw=c.get("ENABLED_DOMAINS", "").strip()
    return [] if not raw else [x.strip().lower() for x in raw.split(",") if x.strip()]

def validate(path):
    errors=[]
    try: c=load_config(path)
    except ConfigError as e: return [str(e)]
    try: require(c,"STATE_DB")
    except ConfigError as e: errors.append(str(e))
    enabled=_enabled(c)
    bad=sorted(set(enabled)-set(DOMAINS))
    if bad: errors.append("unknown enabled domains: "+", ".join(bad))
    requirements={
      "pve":("PVE_API_ENV",), "backup":("PBS_API_ENV",), "ha":("HA_CREDENTIAL_FILE",),
      "zfs":("ZFS_SSH_HOST","ZFS_SSH_USER","ZFS_SSH_KEY","ZFS_KNOWN_HOSTS"),
      "hardware":("HARDWARE_SSH_HOST","HARDWARE_SSH_USER","HARDWARE_SSH_KEY","HARDWARE_KNOWN_HOSTS"),
      "mount":("MOUNT_CATALOG_FILE","MOUNT_SSH_HOST","MOUNT_SSH_USER","MOUNT_SSH_KEY","MOUNT_KNOWN_HOSTS")}
    for d in enabled:
      for k in requirements.get(d,()):
        if not c.get(k,"").strip(): errors.append(f"{d}: missing {k}")
    for k in ("PVE_API_ENV","PBS_API_ENV","HA_CREDENTIAL_FILE","ZFS_SSH_KEY","HARDWARE_SSH_KEY","MOUNT_SSH_KEY"):
      v=c.get(k,"").strip()
      if v and Path(v).exists() and (Path(v).stat().st_mode & (stat.S_IRWXG|stat.S_IRWXO)):
        errors.append(f"{k}: credential/key file permissions are too broad")
    for d in DOMAINS:
      if importlib.util.find_spec(f"rackmarshal.domains.{d}.cycle") is None: errors.append(f"{d}: cycle module unavailable")
      manifest = ROOT / "domains" / d / "plugin.toml"
      try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        if data.get("id", "").lower() != d: errors.append(f"{d}: plugin manifest id mismatch")
        if int(data.get("schema_version", 0)) != 1: errors.append(f"{d}: unsupported plugin manifest schema")
        for name, module in data.get("entrypoints", {}).items():
          if importlib.util.find_spec(module) is None: errors.append(f"{d}: entrypoint {name} unavailable: {module}")
      except Exception as e: errors.append(f"{d}: invalid plugin manifest: {e}")
    return errors

def diagnostic(path):
    c=load_config(path); db=Path(require(c,"STATE_DB")); out={"config":str(path),"state_db":str(db),"state_db_exists":db.exists(),"enabled_domains":_enabled(c)}
    url=f"http://{c.get('STATUS_API_LISTEN_ADDRESS','127.0.0.1')}:{c.get('STATUS_API_LISTEN_PORT','9110')}/health"
    try:
      with urllib.request.urlopen(url,timeout=2) as r: out["health"]={"status":r.status,"body":json.loads(r.read())}
    except Exception as e: out["health"]={"error":f"{type(e).__name__}: {e}"}
    return out

def main(argv=None):
    p=argparse.ArgumentParser(prog="rackmarshal"); p.add_argument("--version",action="version",version=__version__)
    s=p.add_subparsers(dest="cmd",required=True); v=s.add_parser("validate-config"); v.add_argument("--config",default=os.getenv("RACKMARSHAL_CONFIG","/etc/rackmarshal/rackmarshal.conf"))
    s.add_parser("domains")
    d=s.add_parser("diagnostic"); d.add_argument("--config",default=os.getenv("RACKMARSHAL_CONFIG","/etc/rackmarshal/rackmarshal.conf"))
    m=s.add_parser("migrate"); m.add_argument("--config",default=os.getenv("RACKMARSHAL_CONFIG","/etc/rackmarshal/rackmarshal.conf")); m.add_argument("--apply",action="store_true")
    a=p.parse_args(argv)
    if a.cmd=="domains": print("\n".join(DOMAINS)); return 0
    if a.cmd=="diagnostic": print(json.dumps(diagnostic(a.config),indent=2)); return 0
    if a.cmd=="migrate":
      from rackmarshal.db.migrations.migrate import main as migration_main
      old=sys.argv; sys.argv=["rackmarshal-migrate", "--apply" if a.apply else "--plan"] + (["--yes"] if a.apply else [])
      os.environ["RACKMARSHAL_CONFIG"]=a.config
      try: return migration_main() or 0
      finally: sys.argv=old
    errs=validate(a.config); print(json.dumps({"status":"PASS" if not errs else "FAIL","errors":errs},indent=2)); return 0 if not errs else 2
if __name__=="__main__": raise SystemExit(main())
