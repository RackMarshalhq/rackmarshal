#!/usr/bin/env python3
"""RackMarshal schema migration runner (P3 implement).

Default: --plan (read-only).
--apply applies PENDING *.sql in order.
--bootstrap-recorded inserts ledger rows without running SQL (for already-live DBs).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import sys
from pathlib import Path

IMPLEMENT_ENABLED = True

MIG_DIR = Path(__file__).resolve().parent
SQL_RE = re.compile(r"^(\d{3}[a-z]?)_.*\.sql$", re.I)

# Known live set on CT 110 as of 2026-09-17 HARDWARE/MOUNT work
DEFAULT_BOOTSTRAP_IDS = [
    "000_metadata",
    "001_pve_ledger",
    "002_ha_ledger",
    "003_zfs_ledger",
    "004_backup_ledger",
    "005_notify_self",
    "006_hardware_observations",
    "007_mount_ledger",
    "008_hardware_ledger",
    "008b_hardware_incident_processing_cursor",
    "009_hardware_retire_temp_tables",
]


def default_db() -> Path:
    env = os.environ.get("RACKMARSHAL_STATE_DB") or os.environ.get("STATE_DB")
    if env:
        return Path(env)
    try:
        root = MIG_DIR.parent.parent  # /opt/rackmarshal
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from rackmarshal.core.config import load_config, state_db

        return Path(state_db(load_config()))
    except Exception:
        return Path("/var/lib/rackmarshal/state.db")


def migration_id(path: Path) -> str:
    return path.stem


def sort_key(path: Path) -> tuple:
    m = SQL_RE.match(path.name)
    if not m:
        return ("9999", path.name)
    token = m.group(1).lower()
    num = "".join(ch for ch in token if ch.isdigit())
    suffix = "".join(ch for ch in token if ch.isalpha())
    return (num.zfill(4), suffix, path.name)


def discover_sql(mig_dir: Path) -> list[Path]:
    files = [p for p in mig_dir.iterdir() if p.is_file() and SQL_RE.match(p.name)]
    return sorted(files, key=sort_key)


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()



def ensure_db_file(db_path: Path) -> None:
    """Create parent dirs + empty SQLite file if missing (fresh-host drill)."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    print(f"CREATED empty db {db_path}")

def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            checksum TEXT,
            note TEXT
        )
        """
    )


def applied_map(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    ensure_ledger(conn)
    rows = conn.execute(
        "SELECT id, applied_at, checksum, note FROM schema_migrations"
    ).fetchall()
    return {r["id"]: r for r in rows}


def record(conn: sqlite3.Connection, mid: str, dig: str | None, note: str) -> None:
    conn.execute(
        """
        INSERT INTO schema_migrations (id, checksum, note)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (mid, dig, note),
    )


def cmd_plan(db_path: Path, mig_dir: Path) -> int:
    files = discover_sql(mig_dir)
    print(f"DB: {db_path}")
    print(f"Migrations dir: {mig_dir}")
    print(f"IMPLEMENT_ENABLED={IMPLEMENT_ENABLED}")
    print()

    if not db_path.exists():
        print(f"WARN  database missing: {db_path}")
        applied = {}
        conn = None
    else:
        conn = connect(db_path)
        applied = applied_map(conn)

    pending = 0
    for path in files:
        mid = migration_id(path)
        dig = checksum(path)
        if mid in applied:
            row = applied[mid]
            status = "APPLIED"
            extra = f" at {row['applied_at']}"
            if row["checksum"] and row["checksum"] != dig:
                status = "APPLIED-DRIFT"
                extra += " CHECKSUM_MISMATCH"
            if row["note"]:
                extra += f" note={row['note']}"
        else:
            status = "PENDING"
            extra = ""
            pending += 1
        print(f"{status:14} {mid}  sha256={dig[:12]}…{extra}")

    py = mig_dir / "migrate_notify_allow_mount.py"
    if py.exists():
        print()
        print(f"NOTE           {py.name} is a historical one-off (not in SQL runner order)")

    print()
    print(f"PENDING count: {pending}")

    if conn is not None:
        try:
            keys = conn.execute(
                """
                SELECT key, value FROM metadata
                WHERE key LIKE '%ledger%' OR key LIKE '%schema%'
                ORDER BY key
                """
            ).fetchall()
            if keys:
                print()
                print("Legacy metadata (informational):")
                for k, v in keys:
                    print(f"  {k}={v}")
        except sqlite3.Error:
            pass
        conn.close()
    return 0


def cmd_bootstrap(db_path: Path, mig_dir: Path, ids: list[str]) -> int:
    if not IMPLEMENT_ENABLED:
        print("REFUSED: implement disabled", file=sys.stderr)
        return 2
    ensure_db_file(db_path)

    by_id = {migration_id(p): p for p in discover_sql(mig_dir)}
    conn = connect(db_path)
    try:
        ensure_ledger(conn)
        applied = applied_map(conn)
        inserted = 0
        for mid in ids:
            if mid in applied:
                print(f"SKIP   {mid} (already recorded)")
                continue
            path = by_id.get(mid)
            dig = checksum(path) if path else None
            if path is None:
                print(f"WARN   {mid} has no matching .sql on disk; recording anyway")
            record(
                conn,
                mid,
                dig,
                "bootstrap-recorded (already applied before migration runner)",
            )
            print(f"RECORD {mid}")
            inserted += 1
        conn.commit()
        print(f"bootstrap inserted={inserted}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cmd_apply(db_path: Path, mig_dir: Path, yes: bool) -> int:
    if not IMPLEMENT_ENABLED:
        print("REFUSED: implement disabled", file=sys.stderr)
        return 2
    if not yes:
        print("REFUSED: --apply requires --yes", file=sys.stderr)
        return 2
    ensure_db_file(db_path)

    files = discover_sql(mig_dir)
    conn = connect(db_path)
    try:
        applied = applied_map(conn)
        ran = 0
        for path in files:
            mid = migration_id(path)
            if mid in applied:
                continue
            dig = checksum(path)
            sql = path.read_text()
            print(f"APPLY  {mid}")
            try:
                # executescript auto-commits; record immediately after
                conn.executescript(sql)
                ensure_ledger(conn)
                record(conn, mid, dig, "applied by migrate.py")
                conn.commit()
            except Exception as exc:
                print(f"FAIL   {mid}: {exc}", file=sys.stderr)
                return 1
            ran += 1
            print(f"OK     {mid}")
        print(f"apply ran={ran}")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="RackMarshal migration runner")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--migrations-dir", type=Path, default=MIG_DIR)
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--plan", action="store_true", help="Read-only plan (default)")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--bootstrap-recorded", action="store_true")
    parser.add_argument(
        "--ids",
        default=",".join(DEFAULT_BOOTSTRAP_IDS),
        help="Comma-separated ids for --bootstrap-recorded",
    )
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    db_path = args.db or default_db()
    mig_dir = args.migrations_dir

    if args.apply:
        return cmd_apply(db_path, mig_dir, args.yes)
    if args.bootstrap_recorded:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
        return cmd_bootstrap(db_path, mig_dir, ids)
    return cmd_plan(db_path, mig_dir)


if __name__ == "__main__":
    raise SystemExit(main())
