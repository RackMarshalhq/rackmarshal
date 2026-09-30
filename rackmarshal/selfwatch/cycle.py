#!/usr/bin/env python3
"""RackMarshal self-watch cycle (Phase 3 Step 4.4e).

Reads the same freshness/units/notify signals as /status self_watch,
opens/recovers rows in self_incidents, then runs shared enqueue + deliver.

Timer-driven; must include the same domains as /status freshness (incl. MOUNT).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

from rackmarshal.core.config import (
    ha_credential_file,
    install_root,
    state_db,
    venv_python,
)
from rackmarshal.selfwatch.incidents import evaluate_self_signals
from rackmarshal.api.status import (
    build_freshness,
    build_self_watch_notifications,
    build_self_watch_units,
    connect_db,
    latest_generic_observation,
    latest_hardware_observation,
    latest_mount_observation,
    latest_zfs_observation,
)

SCHEMA_VERSION = 1
ORCHESTRATOR_NAME = "self_watch_cycle"

_ROOT = install_root()
PYTHON = str(venv_python())

def module_cmd(name):
    return [PYTHON, "-m", name]

DB = str(state_db())
ENQUEUER = module_cmd("rackmarshal.notifications.queue")
DELIVERY_WORKER = module_cmd("rackmarshal.notifications.delivery")
HA_CREDENTIAL = str(ha_credential_file())


class CycleError(Exception):
    pass


def utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def run_json(command):
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CycleError(
            f"command failed ({result.returncode}): {detail}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CycleError("command returned invalid JSON") from exc


def collect_signals():
    with connect_db() as conn:
        observations = {
            "PVE": latest_generic_observation(
                conn, "pve_cluster_resources"
            ),
            "ZFS": latest_zfs_observation(conn),
            "BACKUP": latest_generic_observation(
                conn, "backup_domain"
            ),
            "HA": latest_generic_observation(
                conn, "home_assistant"
            ),
            "HARDWARE": latest_hardware_observation(conn),
            # M6+: include MOUNT so freshness:MOUNT can recover (parity with /status)
            "MOUNT": latest_mount_observation(conn),
        }
        notifications = build_self_watch_notifications(conn)

        cycle_health_rows = conn.execute(
            """
            SELECT
                unit_name,
                health_state,
                last_result_at,
                last_success_at,
                last_failure_at,
                failure_count,
                last_exit_code,
                last_exit_status
            FROM cycle_health
            ORDER BY unit_name
            """
        ).fetchall()

        cycle_health = {
            row["unit_name"]: {
                "health_state": row["health_state"],
                "last_result_at": row["last_result_at"],
                "last_success_at": row["last_success_at"],
                "last_failure_at": row["last_failure_at"],
                "failure_count": row["failure_count"],
                "last_exit_code": row["last_exit_code"],
                "last_exit_status": row["last_exit_status"],
            }
            for row in cycle_health_rows
        }

    freshness = build_freshness(observations)
    units = build_self_watch_units()
    return freshness, units, notifications, cycle_health


def sync_self_incidents(conn, desired):
    """Mutate one row per signal_key: OPEN desired keys, RECOVER others."""
    now = utc_now()
    desired_by_key = {item["signal_key"]: item for item in desired}

    rows = conn.execute(
        """
        SELECT id, signal_key, incident_state
        FROM self_incidents
        """
    ).fetchall()
    existing = {row["signal_key"]: row for row in rows}

    opened = 0
    reopened = 0
    refreshed = 0
    recovered = 0

    # Open or refresh desired signals
    for key, item in desired_by_key.items():
        detail_json = json.dumps(
            item.get("detail") or {},
            sort_keys=True,
            separators=(",", ":"),
        )
        row = existing.get(key)
        if row is None:
            conn.execute(
                """
                INSERT INTO self_incidents (
                    signal_key,
                    incident_type,
                    severity,
                    incident_state,
                    detail_json,
                    opened_at,
                    recovered_at,
                    last_seen_at
                ) VALUES (?, ?, ?, 'OPEN', ?, ?, NULL, ?)
                """,
                (
                    key,
                    item["incident_type"],
                    item["severity"],
                    detail_json,
                    now,
                    now,
                ),
            )
            opened += 1
            continue

        if row["incident_state"] == "RECOVERED":
            conn.execute(
                """
                UPDATE self_incidents
                SET incident_type = ?,
                    severity = ?,
                    incident_state = 'OPEN',
                    detail_json = ?,
                    opened_at = ?,
                    recovered_at = NULL,
                    last_seen_at = ?
                WHERE id = ?
                """,
                (
                    item["incident_type"],
                    item["severity"],
                    detail_json,
                    now,
                    now,
                    row["id"],
                ),
            )
            reopened += 1
        else:
            conn.execute(
                """
                UPDATE self_incidents
                SET incident_type = ?,
                    severity = ?,
                    detail_json = ?,
                    last_seen_at = ?
                WHERE id = ?
                """,
                (
                    item["incident_type"],
                    item["severity"],
                    detail_json,
                    now,
                    row["id"],
                ),
            )
            refreshed += 1

    # Recover OPEN keys that are no longer desired
    for key, row in existing.items():
        if key in desired_by_key:
            continue
        if row["incident_state"] != "OPEN":
            continue
        conn.execute(
            """
            UPDATE self_incidents
            SET incident_state = 'RECOVERED',
                recovered_at = ?,
                last_seen_at = ?
            WHERE id = ?
            """,
            (now, now, row["id"]),
        )
        recovered += 1

    return {
        "opened": opened,
        "reopened": reopened,
        "refreshed": refreshed,
        "recovered": recovered,
        "desired_count": len(desired_by_key),
    }


def enqueue_notifications():
    result = run_json(ENQUEUER + [ "--db", DB])
    if result.get("schema_version") != SCHEMA_VERSION:
        raise CycleError("unexpected notification enqueuer schema")
    if result.get("consumer") != "incident_notification_enqueuer":
        raise CycleError("unexpected notification enqueuer identity")
    if result.get("status") != "OK":
        raise CycleError("notification enqueuer did not report status=OK")
    return result


def deliver_notifications():
    result = run_json(
        DELIVERY_WORKER + [
            "--db",
            DB,
            "--credential",
            HA_CREDENTIAL,
            "--notification-prefix",
            "rackmarshal",
        ]
    )
    if result.get("schema_version") != SCHEMA_VERSION:
        raise CycleError("unexpected delivery worker schema version")
    if result.get("worker") != "incident_notification_delivery_worker":
        raise CycleError("unexpected delivery worker identity")
    if result.get("status") != "OK":
        raise CycleError("delivery worker did not report status=OK")
    return result


def main():
    freshness, units, notifications, cycle_health = collect_signals()
    desired = evaluate_self_signals(
        freshness,
        units,
        notifications,
        cycle_health,
    )

    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        sync = sync_self_incidents(conn, desired)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    enqueue_result = enqueue_notifications()
    delivery_result = deliver_notifications()

    open_count = 0
    with sqlite3.connect(DB, timeout=10) as c:
        open_count = c.execute(
            """
            SELECT COUNT(*) FROM self_incidents
            WHERE incident_state = 'OPEN'
            """
        ).fetchone()[0]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "runner": ORCHESTRATOR_NAME,
        "status": "OK",
        "observed_at": utc_now(),
        "signals": {
            "freshness": {
                key: value.get("state")
                for key, value in freshness.items()
            },
            "units": units,
            "notifications": notifications,
            "cycle_health": cycle_health,
        },
        "desired_signals": [item["signal_key"] for item in desired],
        "sync": sync,
        "open_self_incidents": open_count,
        "enqueue": {
            "incidents_scanned": enqueue_result.get(
                "incidents_scanned"
            ),
            "notifications_inserted": enqueue_result.get(
                "notifications_inserted"
            ),
        },
        "delivery": {
            "rows_scanned": delivery_result.get("rows_scanned"),
            "sent": delivery_result.get("sent"),
            "failed": delivery_result.get("failed"),
            "fallback_deliveries": delivery_result.get(
                "fallback_deliveries"
            ),
        },
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "runner": ORCHESTRATOR_NAME,
                    "status": "ERROR",
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
