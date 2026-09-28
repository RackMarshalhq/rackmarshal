#!/usr/bin/env python3
"""Conservative retention prune for unreferenced old observation rows."""
from __future__ import annotations
import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from rackmarshal.core.config import load_config, state_db

TABLES=("observations","zfs_observations","mount_observations","hardware_observations")

def prune(db: Path, days: int, now=None):
    if days < 1: raise ValueError("days must be >= 1")
    now=now or datetime.now(timezone.utc)
    cut=(now-timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    con=sqlite3.connect(str(db),timeout=60)
    con.execute("pragma foreign_keys=on"); con.execute("pragma busy_timeout=60000")
    result={}
    try:
        names={r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        for table in TABLES:
            if table not in names: continue
            refs=[]
            for t in names:
                for fk in con.execute(f"pragma foreign_key_list({t})"):
                    if fk[2]==table and fk[4]=="id": refs.append((t,fk[3]))
            clauses=[f"not exists (select 1 from {t} r where r.{col}={table}.id)" for t,col in refs]
            where="observed_at < ?" + (" and "+" and ".join(clauses) if clauses else "")
            before=con.total_changes
            con.execute(f"delete from {table} where {where}",(cut,))
            result[table]=con.total_changes-before
        con.commit()
        if con.execute("pragma quick_check").fetchone()[0]!="ok": raise RuntimeError("quick_check failed")
        return result
    except Exception:
        con.rollback(); raise
    finally:
        con.close()

def main(argv=None):
    cfg=load_config(); p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,default=state_db(cfg))
    p.add_argument("--days",type=int,default=int(os.environ.get("RACKMARSHAL_OBSERVATION_RETAIN_DAYS","35")))
    a=p.parse_args(argv); result=prune(a.db,a.days)
    print("RACKMARSHAL_OBSERVATION_PRUNE_OK "+" ".join(f"{k}={v}" for k,v in sorted(result.items())))
    return 0
if __name__=="__main__": raise SystemExit(main())
