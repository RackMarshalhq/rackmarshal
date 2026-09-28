#!/usr/bin/env python3
"""Recreate incident_notifications CHECK to allow source_domain=MOUNT (M3)."""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/var/lib/rackmarshal/state.db"

NEW_SQL = """
CREATE TABLE incident_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_domain TEXT NOT NULL CHECK (source_domain IN ('PVE', 'ZFS', 'BACKUP', 'HA', 'SELF', 'HARDWARE', 'MOUNT')),
    incident_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL
        CHECK (notification_type IN ('OPENED', 'RECOVERED')),
    delivery_state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (delivery_state IN ('PENDING', 'SENT', 'FAILED')),
    late_discovery INTEGER NOT NULL DEFAULT 0 CHECK (late_discovery IN (0,1)),
    packet_json TEXT,
    explanation_json TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_attempt_at TEXT,
    delivered_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source_domain, incident_id, notification_type),
    CHECK (
        (delivery_state='SENT' AND delivered_at IS NOT NULL)
        OR
        (delivery_state!='SENT' AND delivered_at IS NULL)
    )
)
"""

con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys=OFF")
cur = con.cursor()
row = cur.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='incident_notifications'"
).fetchone()
if not row or not row[0]:
    raise SystemExit("incident_notifications missing")
if "'MOUNT'" in row[0] or '"MOUNT"' in row[0] or "MOUNT" in row[0].split("IN (")[1].split(")")[0]:
    # already allowed
    print("CHECK already allows MOUNT")
    # still verify insert
else:
    cur.execute("ALTER TABLE incident_notifications RENAME TO incident_notifications_pre_mount")
    cur.execute(NEW_SQL)
    cols = (
        "id, source_domain, incident_id, notification_type, delivery_state, "
        "late_discovery, packet_json, explanation_json, attempt_count, "
        "last_attempt_at, delivered_at, last_error, created_at, updated_at"
    )
    cur.execute(
        f"INSERT INTO incident_notifications ({cols}) "
        f"SELECT {cols} FROM incident_notifications_pre_mount"
    )
    cur.execute("DROP TABLE incident_notifications_pre_mount")
    con.commit()
    print("migrated CHECK to allow MOUNT")

# dry insert/delete
cur.execute(
    "INSERT INTO incident_notifications (source_domain, incident_id, notification_type, delivery_state) "
    "VALUES ('MOUNT', 0, 'OPENED', 'PENDING')"
)
nid = cur.lastrowid
cur.execute("DELETE FROM incident_notifications WHERE id=?", (nid,))
con.commit()
print("dry INSERT MOUNT OK")
con.close()
