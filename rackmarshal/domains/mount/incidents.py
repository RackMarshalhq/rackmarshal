#!/usr/bin/env python3
"""Sync mount_incidents from the latest mount_observations payload (M5)."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("/var/lib/rackmarshal/state.db")

STATE_TO_TYPE = {
    "missing": "MOUNT_MISSING",
    "wrong_source": "MOUNT_WRONG_SOURCE",
    "unreadable": "MOUNT_UNREADABLE",
    "export_stale": "MOUNT_EXPORT_STALE",
    "guest_unreachable": "MOUNT_MISSING",
}

OUTCOME_FOR_STATE = {
    "missing": "MISSING",
    "wrong_source": "WRONG_SOURCE",
    "unreadable": "UNREADABLE",
    "export_stale": "EXPORT_STALE",
    "guest_unreachable": "MISSING",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def latest_observation(con: sqlite3.Connection):
    return con.execute(
        """
        SELECT id, observed_at, payload_json
        FROM mount_observations
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def desired_problems(payload: dict) -> dict[str, dict]:
    """mount_id -> result row for actionable problems."""
    out = {}
    for row in payload.get("results") or []:
        state = row.get("state")
        if state not in STATE_TO_TYPE:
            continue
        if row.get("optional"):
            continue
        mid = row.get("id")
        if not mid:
            continue
        out[mid] = row
    return out


def open_incidents(con: sqlite3.Connection) -> dict[tuple[str, str], sqlite3.Row]:
    rows = con.execute(
        """
        SELECT *
        FROM mount_incidents
        WHERE incident_state = 'OPEN'
        """
    ).fetchall()
    return {(r["mount_id"], r["incident_type"]): r for r in rows}


def insert_event(con, observation_id, row, outcome, observed_at) -> int:
    changes = {
        "state": row.get("state"),
        "expected_source": row.get("expected_source"),
        "observed_source": row.get("observed_source"),
        "detail": row.get("detail"),
    }
    cur = con.execute(
        """
        INSERT INTO mount_events (
            observation_id, mount_id, guest_kind, guest_id, mountpoint,
            outcome, expected_source, observed_source, fstype,
            changes_json, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            row["id"],
            row.get("guest_kind") or "host",
            str(row.get("guest_id") or ""),
            row.get("mountpoint") or "",
            outcome,
            row.get("expected_source"),
            row.get("observed_source"),
            row.get("fstype"),
            json.dumps(changes, separators=(",", ":"), sort_keys=True),
            observed_at,
        ),
    )
    return int(cur.lastrowid)


def severity_for(row: dict) -> str:
    sev = (row.get("severity_missing") or "warning").lower()
    if sev in ("info", "warning", "critical", "urgent"):
        return sev
    return "warning"


def open_one(con, observation_id, row, observed_at) -> int:
    itype = STATE_TO_TYPE[row["state"]]
    outcome = OUTCOME_FOR_STATE[row["state"]]
    eid = insert_event(con, observation_id, row, outcome, observed_at)
    display = row.get("id")
    changes = json.dumps(row, separators=(",", ":"), sort_keys=True)
    cur = con.execute(
        """
        INSERT INTO mount_incidents (
            mount_id, guest_kind, guest_id, mountpoint, display_name,
            incident_type, severity, incident_state,
            opened_event_id, last_event_id,
            opened_observation_id, last_abnormal_observation_id,
            opened_at, last_abnormal_at,
            opening_changes_json, latest_changes_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            row.get("guest_kind") or "host",
            str(row.get("guest_id") or ""),
            row.get("mountpoint") or "",
            display,
            itype,
            severity_for(row),
            eid,
            eid,
            observation_id,
            observation_id,
            observed_at,
            observed_at,
            changes,
            changes,
        ),
    )
    iid = int(cur.lastrowid)
    con.execute(
        """
        INSERT OR REPLACE INTO mount_incident_processing (incident_id, last_processed_event_id)
        VALUES (?, ?)
        """,
        (iid, eid),
    )
    return iid


def touch_open(con, incident: sqlite3.Row, observation_id, row, observed_at) -> None:
    outcome = OUTCOME_FOR_STATE[row["state"]]
    eid = insert_event(con, observation_id, row, outcome, observed_at)
    changes = json.dumps(row, separators=(",", ":"), sort_keys=True)
    con.execute(
        """
        UPDATE mount_incidents
        SET last_event_id = ?,
            last_abnormal_observation_id = ?,
            last_abnormal_at = ?,
            latest_changes_json = ?,
            severity = ?,
            occurrence_count = occurrence_count + 1,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE id = ?
        """,
        (
            eid,
            observation_id,
            observed_at,
            changes,
            severity_for(row),
            incident["id"],
        ),
    )
    con.execute(
        """
        INSERT OR REPLACE INTO mount_incident_processing (incident_id, last_processed_event_id)
        VALUES (?, ?)
        """,
        (incident["id"], eid),
    )


def recover_one(con, incident: sqlite3.Row, observation_id, observed_at, ok_row: dict | None) -> None:
    row = ok_row or {
        "id": incident["mount_id"],
        "guest_kind": incident["guest_kind"],
        "guest_id": incident["guest_id"],
        "mountpoint": incident["mountpoint"],
        "expected_source": None,
        "observed_source": None,
        "fstype": None,
        "state": "ok",
        "detail": "recovered",
    }
    eid = insert_event(con, observation_id, row, "RECOVERED", observed_at)
    con.execute(
        """
        UPDATE mount_incidents
        SET incident_state = 'RECOVERED',
            last_event_id = ?,
            recovered_observation_id = ?,
            recovered_at = ?,
            latest_changes_json = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE id = ?
        """,
        (
            eid,
            observation_id,
            observed_at,
            json.dumps({"state": "ok"}, separators=(",", ":")),
            incident["id"],
        ),
    )
    con.execute(
        """
        INSERT OR REPLACE INTO mount_incident_processing (incident_id, last_processed_event_id)
        VALUES (?, ?)
        """,
        (incident["id"], eid),
    )


def process(con: sqlite3.Connection) -> dict:
    obs = latest_observation(con)
    if obs is None:
        return {"status": "OK", "opened": 0, "updated": 0, "recovered": 0, "note": "no_observations"}
    prev = con.execute(
        "SELECT value FROM metadata WHERE key='mount_last_processed_observation_id'"
    ).fetchone()
    if prev and str(prev[0]) == str(obs["id"]):
        open_n = con.execute(
            "SELECT COUNT(*) FROM mount_incidents WHERE incident_state='OPEN'"
        ).fetchone()[0]
        return {
            "status": "OK",
            "consumer": "mount_incident_processor",
            "observation_id": obs["id"],
            "opened": 0,
            "updated": 0,
            "recovered": 0,
            "open_problems": open_n,
            "note": "already_processed",
        }
    payload = json.loads(obs["payload_json"])
    problems = desired_problems(payload)
    # index ok rows for recovery context
    ok_by_id = {
        r["id"]: r
        for r in (payload.get("results") or [])
        if r.get("state") == "ok" and r.get("id")
    }
    open_map = open_incidents(con)
    opened = updated = recovered = 0
    observed_at = obs["observed_at"]
    oid = obs["id"]

    # open or update
    for mid, row in problems.items():
        itype = STATE_TO_TYPE[row["state"]]
        key = (mid, itype)
        if key in open_map:
            touch_open(con, open_map[key], oid, row, observed_at)
            updated += 1
        else:
            # if another type is open for same mount, leave it; open new type
            open_one(con, oid, row, observed_at)
            opened += 1

    # recover opens no longer desired
    for key, inc in list(open_map.items()):
        mid, itype = key
        if mid in problems and STATE_TO_TYPE[problems[mid]["state"]] == itype:
            continue
        # Missing/unknown telemetry is not independent positive recovery evidence.
        if mid not in ok_by_id:
            continue
        recover_one(con, inc, oid, observed_at, ok_by_id[mid])
        recovered += 1

    con.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('mount_last_processed_observation_id', ?)",
        (str(oid),),
    )
    con.commit()
    return {
        "status": "OK",
        "consumer": "mount_incident_processor",
        "observation_id": oid,
        "opened": opened,
        "updated": updated,
        "recovered": recovered,
        "open_problems": con.execute("SELECT COUNT(*) FROM mount_incidents WHERE incident_state='OPEN'").fetchone()[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    con = connect(args.db)
    try:
        result = process(con)
    finally:
        con.close()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"mount incidents: opened={result['opened']} "
            f"updated={result['updated']} recovered={result['recovered']} "
            f"problems={result['open_problems']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
