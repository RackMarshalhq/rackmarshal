"""Conservative retention prune for observation tables.

Deletes observation rows older than the retention window that nothing else
references, in small batches. It always keeps the newest row of each table (the
newest per collector for the shared observations table), so a collector that
stopped for a long time does not lose its last known state.

    python -m rackmarshal.maintenance.prune [--dry-run] [--days N]

Reads RACKMARSHAL_STATE_DB (default /var/lib/rackmarshal/state.db) and
RACKMARSHAL_OBSERVATION_RETAIN_DAYS (default 35, minimum 7).
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
import sqlite3
import sys

DEFAULT_DAYS = 35
MIN_DAYS = 7
BATCH = 5000
TABLES = ("observations", "zfs_observations", "mount_observations", "hardware_observations")


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _references(connection, table):
    """(child table, column) pairs whose foreign key points at table.id."""
    refs = []
    names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for child in names:
        for fk in connection.execute("PRAGMA foreign_key_list(%s)" % _quote(child)):
            if fk[2] == table and fk[4] == "id":
                refs.append((child, fk[3]))
    return refs


def _keep_newest(connection, table):
    columns = [row[1] for row in connection.execute("PRAGMA table_info(%s)" % _quote(table))]
    if "collector" in columns:
        return "id NOT IN (SELECT MAX(id) FROM %s GROUP BY collector)" % _quote(table)
    return "id <> (SELECT MAX(id) FROM %s)" % _quote(table)


def prune(db_path, days=DEFAULT_DAYS, dry_run=False, now=None, batch=BATCH):
    """Returns {table: rows deleted (or that would be deleted)}; raises if the database fails quick_check."""
    if days < MIN_DAYS:
        raise ValueError("retention must be at least %d days" % MIN_DAYS)
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    result = {}
    with closing(sqlite3.connect(db_path, timeout=60)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=60000")
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TABLES:
            if table not in existing:
                continue
            clauses = ["observed_at < ?", _keep_newest(connection, table)]
            clauses += ["NOT EXISTS (SELECT 1 FROM %s r WHERE r.%s = %s.id)" % (_quote(child), _quote(col), _quote(table))
                        for child, col in _references(connection, table)]
            where = " AND ".join(clauses)
            if dry_run:
                result[table] = connection.execute(
                    "SELECT COUNT(*) FROM %s WHERE %s" % (_quote(table), where), (cutoff,)).fetchone()[0]
                continue
            total = 0
            while True:
                cursor = connection.execute(
                    "DELETE FROM %s WHERE id IN (SELECT id FROM %s WHERE %s ORDER BY id LIMIT ?)"
                    % (_quote(table), _quote(table), where), (cutoff, batch))
                connection.commit()
                total += cursor.rowcount
                if cursor.rowcount < batch:
                    break
            result[table] = total
        if not dry_run:
            check = connection.execute("PRAGMA quick_check").fetchall()
            if check != [("ok",)]:
                raise RuntimeError("quick_check failed after prune")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="count rows that would be deleted; change nothing")
    parser.add_argument("--days", type=int,
                        default=int(os.environ.get("RACKMARSHAL_OBSERVATION_RETAIN_DAYS", DEFAULT_DAYS)))
    args = parser.parse_args(argv)
    db = os.environ.get("RACKMARSHAL_STATE_DB", "/var/lib/rackmarshal/state.db")
    try:
        result = prune(db, args.days, args.dry_run)
    except (ValueError, RuntimeError, sqlite3.Error, OSError) as exc:
        print("PRUNE FAILED: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1
    verb = "would delete" if args.dry_run else "deleted"
    for table, count in result.items():
        print("%s: %s %d rows older than %d days" % (table, verb, count, args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
