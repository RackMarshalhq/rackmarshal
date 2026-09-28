#!/usr/bin/env python3
"""Online-safe RackMarshal state database snapshot and retention."""
from __future__ import annotations
import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rackmarshal.core.config import load_config, state_db, state_dir

def create_snapshot(db: Path, out: Path, retention: int) -> Path:
    if retention < 1:
        raise ValueError("retention must be >= 1")
    if not db.is_file():
        raise FileNotFoundError(db)
    out.mkdir(parents=True, exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    dest=out/f"state.db.{stamp}"
    tmp=out/f".{dest.name}.tmp"
    if tmp.exists(): tmp.unlink()
    src=sqlite3.connect(str(db), timeout=60)
    dst=sqlite3.connect(str(tmp), timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    check=sqlite3.connect(str(tmp))
    try:
        if check.execute("pragma quick_check").fetchone()[0] != "ok":
            raise RuntimeError("snapshot quick_check failed")
    finally:
        check.close()
    os.replace(tmp,dest)
    latest=out/"state.db.latest"
    latest.write_bytes(dest.read_bytes())
    snapshots=sorted(out.glob("state.db.20*Z"), key=lambda p:p.stat().st_mtime, reverse=True)
    for old in snapshots[retention:]: old.unlink()
    return dest

def main(argv=None):
    cfg=load_config()
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,default=state_db(cfg))
    p.add_argument("--out",type=Path,default=state_dir(cfg)/"db-snapshots")
    p.add_argument("--retention",type=int,default=int(os.environ.get("RACKMARSHAL_DB_SNAPSHOT_RETENTION","14")))
    a=p.parse_args(argv)
    dest=create_snapshot(a.db,a.out,a.retention)
    print(f"RACKMARSHAL_DB_SNAPSHOT_OK path={dest}")
    return 0
if __name__=="__main__": raise SystemExit(main())
