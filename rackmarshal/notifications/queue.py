#!/usr/bin/env python3

import argparse
import json
import sqlite3
import subprocess
import sys

from rackmarshal.core.config import state_db, install_root
from rackmarshal.notifications.policy import should_enqueue


DEFAULT_DB = str(state_db())
# Phase 2 Step 15: derive DEFAULT_BUILDER from config helpers
# (defaults = today's layout).
DEFAULT_BUILDER = [sys.executable, "-m", "rackmarshal.incidents.packet"]

SCHEMA_VERSION = 1
CONSUMER = "incident_notification_enqueuer"


class EnqueueError(Exception):
    pass


def build_packet(
    builder,
    db_path,
    domain,
    incident_id,
    notification_type,
):
    command = list(builder) + [
        "--db",
        db_path,
        "--domain",
        domain,
        "--incident-id",
        str(incident_id),
        "--notification-type",
        notification_type,
    ]

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or "packet builder failed"
        )

        raise EnqueueError(
            f"packet build failed for "
            f"{domain} incident {incident_id} "
            f"{notification_type}: {detail}"
        )

    try:
        packet = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EnqueueError(
            "packet builder returned invalid JSON"
        ) from exc

    if not isinstance(packet, dict):
        raise EnqueueError(
            "packet builder did not return object"
        )

    if packet.get("schema_version") != 1:
        raise EnqueueError(
            "unexpected packet schema_version"
        )

    if packet.get("builder") != \
            "incident_notification_packet":
        raise EnqueueError(
            "unexpected packet builder identity"
        )

    if packet.get("source_domain") != domain:
        raise EnqueueError(
            "packet domain mismatch"
        )

    if packet.get("incident_id") != incident_id:
        raise EnqueueError(
            "packet incident_id mismatch"
        )

    if packet.get("notification_type") != \
            notification_type:
        raise EnqueueError(
            "packet notification_type mismatch"
        )

    return packet


def incident_rows(db):
    rows = []

    for domain, table in (
        ("PVE", "resource_incidents"),
        ("ZFS", "zfs_incidents"),
        ("BACKUP", "backup_incidents"),
        ("HA", "ha_incidents"),
        ("SELF", "self_incidents"),
        ("MOUNT", "mount_incidents"),
        ("HARDWARE", "hardware_incidents"),
    ):
        found = db.execute(
            f"""
            SELECT
                id,
                incident_state
            FROM {table}
            ORDER BY id
            """
        ).fetchall()

        for row in found:
            rows.append(
                {
                    "domain": domain,
                    "incident_id": row["id"],
                    "incident_state":
                        row["incident_state"],
                }
            )


    return rows


def notification_exists(
    db,
    domain,
    incident_id,
    notification_type,
):
    row = db.execute(
        """
        SELECT 1
        FROM incident_notifications
        WHERE source_domain=?
          AND incident_id=?
          AND notification_type=?
        """,
        (
            domain,
            incident_id,
            notification_type,
        ),
    ).fetchone()

    return row is not None


def enqueue_one(
    db,
    db_path,
    builder,
    domain,
    incident_id,
    incident_state,
):
    if incident_state == "OPEN":
        notification_type = "OPENED"

        if notification_exists(
            db,
            domain,
            incident_id,
            notification_type,
        ):
            return 0

        late_discovery = 0

    elif incident_state == "RECOVERED":
        notification_type = "RECOVERED"

        if notification_exists(
            db,
            domain,
            incident_id,
            notification_type,
        ):
            return 0

        late_discovery = (
            0
            if notification_exists(
                db,
                domain,
                incident_id,
                "OPENED",
            )
            else 1
        )

    else:
        raise EnqueueError(
            f"unsupported incident state: "
            f"{incident_state}"
        )

    # Phase 3 Step 3: central notify policy gate (defaults = allow all).
    decision = should_enqueue(notification_type)
    if not decision.allow:
        return 0

    packet = build_packet(
        builder,
        db_path,
        domain,
        incident_id,
        notification_type,
    )

    encoded = json.dumps(
        packet,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    before = db.total_changes

    db.execute(
        """
        INSERT OR IGNORE
        INTO incident_notifications (
            source_domain,
            incident_id,
            notification_type,
            delivery_state,
            late_discovery,
            packet_json
        )
        VALUES (
            ?,
            ?,
            ?,
            'PENDING',
            ?,
            ?
        )
        """,
        (
            domain,
            incident_id,
            notification_type,
            late_discovery,
            encoded,
        ),
    )

    return db.total_changes - before


def run_cycle(
    db_path,
    builder,
):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")

    inserted = 0
    scanned = 0

    try:
        incidents = incident_rows(db)

        db.execute("BEGIN IMMEDIATE")

        for incident in incidents:
            scanned += 1

            inserted += enqueue_one(
                db,
                db_path,
                builder,
                incident["domain"],
                incident["incident_id"],
                incident["incident_state"],
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return {
        "schema_version": SCHEMA_VERSION,
        "consumer": CONSUMER,
        "status": "OK",
        "incidents_scanned": scanned,
        "notifications_inserted": inserted,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Enqueue deterministic RackMarshal "
            "incident notifications."
        )
    )

    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
    )

    parser.add_argument(
        "--builder",
        default=DEFAULT_BUILDER,
    )

    args = parser.parse_args()

    try:
        result = run_cycle(
            args.db,
            args.builder,
        )

    except (
        EnqueueError,
        sqlite3.Error,
    ) as exc:
        print(
            json.dumps(
                {
                    "schema_version":
                        SCHEMA_VERSION,
                    "consumer":
                        CONSUMER,
                    "status":
                        "failed",
                    "error":
                        str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )

        return 1

    print(
        json.dumps(
            result,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
