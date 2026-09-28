#!/usr/bin/env python3
"""HARDWARE incident processor (Step G).

Observation-driven compare/streaks → hardware_events + hardware_incidents.
Streaks live in hardware_device_state (specialized temperature tables retired).
Open/recovered identity: hardware_incidents only.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rackmarshal.core.config import load_config, require, state_db

PROCESSOR_KEY = "hardware_incident_processor"
CONFIG = load_config()
DB = str(state_db(CONFIG))

HOT_THRESHOLD = float(require(CONFIG, "HARDWARE_HOT_THRESHOLD_C"))
HOT_REQUIRED_SAMPLES = int(require(CONFIG, "HARDWARE_HOT_REQUIRED_SAMPLES"))
URGENT_THRESHOLD = float(require(CONFIG, "HARDWARE_URGENT_THRESHOLD_C"))
RECOVERY_THRESHOLD = float(require(CONFIG, "HARDWARE_RECOVERY_THRESHOLD_C"))
RECOVERY_REQUIRED_SAMPLES = int(require(CONFIG, "HARDWARE_RECOVERY_REQUIRED_SAMPLES"))


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def ensure_cursor(con: sqlite3.Connection) -> None:
    con.execute(
        """
        INSERT OR IGNORE INTO hardware_incident_processing (
            processor_key, last_processed_observation_id
        ) VALUES (?, NULL)
        """,
        (PROCESSOR_KEY,),
    )


def get_watermark(con: sqlite3.Connection):
    ensure_cursor(con)
    row = con.execute(
        "SELECT last_processed_observation_id FROM hardware_incident_processing WHERE processor_key=?",
        (PROCESSOR_KEY,),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def set_watermark(con: sqlite3.Connection, obs_id: int) -> None:
    ensure_cursor(con)
    con.execute(
        """
        UPDATE hardware_incident_processing
        SET last_processed_observation_id=?,
            updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE processor_key=?
        """,
        (obs_id, PROCESSOR_KEY),
    )


def ensure_device_state_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS hardware_device_state (
            serial TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            role TEXT NOT NULL,
            hot_streak INTEGER NOT NULL DEFAULT 0 CHECK (hot_streak >= 0),
            cool_streak INTEGER NOT NULL DEFAULT 0 CHECK (cool_streak >= 0),
            last_observed_at TEXT,
            last_temperature_c REAL,
            maximum_temperature_c REAL,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
        """
    )


def incident_type_for(severity: str) -> str:
    if severity == "MISSING":
        return "HARDWARE_MISSING"
    if severity == "URGENT":
        return "HARDWARE_TEMP_URGENT"
    return "HARDWARE_TEMP_HOT"


def has_open_incident(con, serial: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM hardware_incidents WHERE serial=? AND incident_state='OPEN'",
        (serial,),
    ).fetchone()
    return row is not None


def open_severity(con, serial: str):
    row = con.execute(
        "SELECT severity FROM hardware_incidents WHERE serial=? AND incident_state='OPEN'",
        (serial,),
    ).fetchone()
    return row["severity"] if row else None


def insert_hardware_event(con, observation_id, serial, role, model, outcome, severity, temp, observed_at, changes):
    row = con.execute(
        "SELECT id FROM hardware_events WHERE observation_id=? AND serial=? AND outcome=?",
        (observation_id, serial, outcome),
    ).fetchone()
    if row:
        return int(row[0])
    cur = con.execute(
        """
        INSERT INTO hardware_events (
            observation_id, serial, role, model, outcome, severity, temperature_c,
            changes_json, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            serial,
            role,
            model,
            outcome,
            severity,
            temp,
            json.dumps(changes, sort_keys=True),
            observed_at,
        ),
    )
    return int(cur.lastrowid)


def open_incident_row(con, serial, role, model, severity, event_id, obs_id, observed_at, changes):
    existing = con.execute(
        "SELECT id FROM hardware_incidents WHERE serial=? AND incident_state='OPEN'",
        (serial,),
    ).fetchone()
    if existing:
        return int(existing[0]), False
    cur = con.execute(
        """
        INSERT INTO hardware_incidents (
            serial, role, model, incident_type, severity, incident_state,
            opened_event_id, last_event_id,
            opened_observation_id, last_abnormal_observation_id,
            opened_at, last_abnormal_at, occurrence_count,
            opening_changes_json, latest_changes_json
        ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            serial,
            role,
            model,
            incident_type_for(severity),
            severity,
            event_id,
            event_id,
            obs_id,
            obs_id,
            observed_at,
            observed_at,
            json.dumps(changes, sort_keys=True),
            json.dumps(changes, sort_keys=True),
        ),
    )
    return int(cur.lastrowid), True


def escalate_incident_row(con, serial, severity, event_id, obs_id, observed_at, changes):
    row = con.execute(
        "SELECT id FROM hardware_incidents WHERE serial=? AND incident_state='OPEN'",
        (serial,),
    ).fetchone()
    if not row:
        return None, False
    con.execute(
        """
        UPDATE hardware_incidents
        SET severity=?,
            incident_type=?,
            last_event_id=?,
            last_abnormal_observation_id=?,
            last_abnormal_at=?,
            latest_changes_json=?,
            occurrence_count=occurrence_count+1,
            updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE id=?
        """,
        (
            severity,
            incident_type_for(severity),
            event_id,
            obs_id,
            observed_at,
            json.dumps(changes, sort_keys=True),
            int(row[0]),
        ),
    )
    return int(row[0]), True


def recover_incident_row(con, serial, event_id, obs_id, observed_at, changes):
    row = con.execute(
        "SELECT id FROM hardware_incidents WHERE serial=? AND incident_state='OPEN'",
        (serial,),
    ).fetchone()
    if not row:
        return None, False
    con.execute(
        """
        UPDATE hardware_incidents
        SET incident_state='RECOVERED',
            last_event_id=?,
            recovered_observation_id=?,
            recovered_at=?,
            latest_changes_json=?,
            updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE id=?
        """,
        (
            event_id,
            obs_id,
            observed_at,
            json.dumps(changes, sort_keys=True),
            int(row[0]),
        ),
    )
    return int(row[0]), True


def process_observation(con, obs) -> dict:
    out = {"opened": 0, "escalated": 0, "recovered": 0, "events": 0}
    serial = obs["serial"]
    role = obs["role"]
    model = obs["model"] or ""
    temp = obs["temperature_c"]
    observed_at = obs["observed_at"]
    obs_id = int(obs["id"])
    sample_status = obs["status"]

    state = con.execute(
        "SELECT * FROM hardware_device_state WHERE serial=?", (serial,)
    ).fetchone()
    if state is None:
        con.execute(
            "INSERT INTO hardware_device_state (serial, model, role) VALUES (?, ?, ?)",
            (serial, model, role),
        )
        state = con.execute(
            "SELECT * FROM hardware_device_state WHERE serial=?", (serial,)
        ).fetchone()

    hot_streak = int(state["hot_streak"])
    cool_streak = int(state["cool_streak"])
    maximum = state["maximum_temperature_c"]
    is_open = has_open_incident(con, serial)
    severity = open_severity(con, serial)

    if maximum is None and temp is not None:
        maximum = temp
    elif temp is not None and (maximum is None or temp > maximum):
        maximum = temp

    new_event = None  # (event_type, severity)

    if sample_status == "MISSING":
        hot_streak = 0
        cool_streak = 0
        if not is_open:
            new_event = ("OPENED", "MISSING")
    elif sample_status == "URGENT":
        hot_streak += 1
        cool_streak = 0
        if not is_open:
            new_event = ("OPENED", "URGENT")
        elif severity != "URGENT":
            new_event = ("ESCALATED", "URGENT")
    elif sample_status == "HOT":
        hot_streak += 1
        cool_streak = 0
        if not is_open and hot_streak >= HOT_REQUIRED_SAMPLES:
            new_event = ("OPENED", "HOT")
    else:  # OK
        hot_streak = 0
        if temp is not None and temp <= RECOVERY_THRESHOLD:
            cool_streak += 1
        else:
            cool_streak = 0
        if is_open and cool_streak >= RECOVERY_REQUIRED_SAMPLES:
            new_event = ("RECOVERED", None)

    if new_event and new_event[0] == "OPENED":
        out["opened"] = 1
    if new_event and new_event[0] == "ESCALATED":
        out["escalated"] = 1
    if new_event and new_event[0] == "RECOVERED":
        out["recovered"] = 1

    con.execute(
        """
        UPDATE hardware_device_state
        SET model=?, role=?,
            hot_streak=?, cool_streak=?,
            last_observed_at=?, last_temperature_c=?,
            maximum_temperature_c=?,
            updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE serial=?
        """,
        (
            model or state["model"],
            role,
            hot_streak,
            cool_streak,
            observed_at,
            temp,
            maximum,
            serial,
        ),
    )

    if new_event:
        event_type, ev_sev = new_event
        details = {
            "sample_status": sample_status,
            "hot_streak": hot_streak,
            "cool_streak": cool_streak,
            "hot_threshold": HOT_THRESHOLD,
            "urgent_threshold": URGENT_THRESHOLD,
            "recovery_threshold": RECOVERY_THRESHOLD,
            "temperature_c": temp,
            "observation_id": obs_id,
        }
        outcome = event_type
        he_id = insert_hardware_event(
            con,
            obs_id,
            serial,
            role,
            model,
            outcome,
            ev_sev,
            temp,
            observed_at,
            details,
        )
        out["events"] = 1
        if event_type == "OPENED":
            open_incident_row(
                con, serial, role, model, ev_sev, he_id, obs_id, observed_at, details
            )
        elif event_type == "ESCALATED":
            escalate_incident_row(
                con, serial, ev_sev, he_id, obs_id, observed_at, details
            )
        elif event_type == "RECOVERED":
            recover_incident_row(
                con, serial, he_id, obs_id, observed_at, details
            )

    return out


def process() -> dict:
    con = connect()
    try:
        ensure_device_state_table(con)
        ensure_cursor(con)
        wm = get_watermark(con)
        latest_row = con.execute("SELECT MAX(id) FROM hardware_observations").fetchone()
        latest = latest_row[0]
        if latest is None:
            return {
                "status": "OK",
                "consumer": "hardware_incident_processor",
                "opened": 0,
                "escalated": 0,
                "recovered": 0,
                "processed": 0,
                "open_incidents": 0,
                "watermark": wm,
                "note": "no_observations",
            }
        latest = int(latest)
        if wm is not None and wm >= latest:
            open_n = con.execute(
                "SELECT COUNT(*) FROM hardware_incidents WHERE incident_state='OPEN'"
            ).fetchone()[0]
            return {
                "status": "OK",
                "consumer": "hardware_incident_processor",
                "opened": 0,
                "escalated": 0,
                "recovered": 0,
                "processed": 0,
                "open_incidents": open_n,
                "watermark": wm,
                "latest_observation_id": latest,
                "note": "already_processed",
            }

        if wm is None:
            set_watermark(con, latest)
            con.commit()
            open_n = con.execute(
                "SELECT COUNT(*) FROM hardware_incidents WHERE incident_state='OPEN'"
            ).fetchone()[0]
            return {
                "status": "OK",
                "consumer": "hardware_incident_processor",
                "opened": 0,
                "escalated": 0,
                "recovered": 0,
                "processed": 0,
                "open_incidents": open_n,
                "watermark": latest,
                "latest_observation_id": latest,
                "note": "cursor_initialized_skip_backfill",
            }

        rows = con.execute(
            """
            SELECT * FROM hardware_observations
            WHERE id > ?
            ORDER BY id
            """,
            (wm,),
        ).fetchall()

        totals = {"opened": 0, "escalated": 0, "recovered": 0, "processed": 0}
        max_id = wm
        for obs in rows:
            r = process_observation(con, obs)
            totals["opened"] += r["opened"]
            totals["escalated"] += r["escalated"]
            totals["recovered"] += r["recovered"]
            totals["processed"] += 1
            max_id = int(obs["id"])
        set_watermark(con, max_id)
        con.commit()
        open_n = con.execute(
            "SELECT COUNT(*) FROM hardware_incidents WHERE incident_state='OPEN'"
        ).fetchone()[0]
        return {
            "status": "OK",
            "consumer": "hardware_incident_processor",
            "opened": totals["opened"],
            "escalated": totals["escalated"],
            "recovered": totals["recovered"],
            "processed": totals["processed"],
            "open_incidents": open_n,
            "watermark": max_id,
            "latest_observation_id": latest,
            "note": "observation_driven_stepG",
        }
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def main():
    result = process()
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    if result.get("status") != "OK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
