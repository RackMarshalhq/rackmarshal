#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys

from rackmarshal.core.config import state_db


DEFAULT_DB = str(state_db())

SCHEMA_VERSION = 1
BUILDER = "incident_notification_packet"


class PacketError(Exception):
    pass


def load_changes(value):
    try:
        data = json.loads(value)
    except (
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise PacketError(
            f"invalid changes JSON: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise PacketError(
            "changes JSON must be an array"
        )

    return data


def find_change(changes, field):
    for change in changes:
        if (
            isinstance(change, dict)
            and change.get("field") == field
        ):
            return change

    return None


def changes_note(changes):
    parts = []

    for change in changes:
        if not isinstance(change, dict):
            continue

        field = change.get("field")
        expected = change.get("expected")
        actual = change.get("actual")

        parts.append(
            f"{field}: expected {expected!r}, "
            f"actual {actual!r}"
        )

    if not parts:
        return None

    return "; ".join(parts)


def zfs_expected_state(
    db,
    resource_type,
    pool_name,
    vdev_name,
):
    if resource_type == "zfs_pool":
        row = db.execute(
            """
            SELECT expected_state
            FROM zfs_pool_baseline
            WHERE pool_name=?
            """,
            (pool_name,),
        ).fetchone()

    elif resource_type == "zfs_vdev":
        row = db.execute(
            """
            SELECT expected_state
            FROM zfs_vdev_baseline
            WHERE pool_name=?
              AND vdev_name=?
            """,
            (
                pool_name,
                vdev_name,
            ),
        ).fetchone()

    else:
        raise PacketError(
            f"unsupported ZFS resource_type: "
            f"{resource_type}"
        )

    if row is None:
        return None

    return row["expected_state"]


def build_pve(db, incident_id):
    row = db.execute(
        """
        SELECT
            id,
            resource_type,
            resource_key,
            display_name,
            incident_type,
            incident_state,
            baseline_state,
            expected_status,
            abnormal_status,
            opened_at,
            last_abnormal_at,
            recovered_at,
            occurrence_count,
            note
        FROM resource_incidents
        WHERE id=?
        """,
        (incident_id,),
    ).fetchone()

    if row is None:
        raise PacketError(
            f"PVE incident {incident_id} not found"
        )

    display_name = (
        row["display_name"]
        or row["resource_key"]
    )

    incident = {
        "resource_type":
            row["resource_type"],
        "resource_key":
            row["resource_key"],
        "display_name":
            display_name,
        "incident_type":
            row["incident_type"],
        "baseline_state":
            row["baseline_state"],
        "expected_status":
            row["expected_status"],
        "actual_status":
            row["abnormal_status"],
        "occurrence_count":
            row["occurrence_count"],
        "opened_at":
            row["opened_at"],
        "last_abnormal_at":
            row["last_abnormal_at"],
    }

    if row["note"] is not None:
        incident["note"] = row["note"]

    return row, incident


def build_zfs(db, incident_id):
    row = db.execute(
        """
        SELECT
            id,
            resource_type,
            resource_key,
            pool_name,
            vdev_name,
            incident_type,
            incident_state,
            baseline_state,
            opened_at,
            last_abnormal_at,
            recovered_at,
            occurrence_count,
            latest_changes_json,
            note
        FROM zfs_incidents
        WHERE id=?
        """,
        (incident_id,),
    ).fetchone()

    if row is None:
        raise PacketError(
            f"ZFS incident {incident_id} not found"
        )

    changes = load_changes(
        row["latest_changes_json"]
    )

    expected_status = zfs_expected_state(
        db,
        row["resource_type"],
        row["pool_name"],
        row["vdev_name"],
    )

    actual_status = None

    state_change = find_change(
        changes,
        "state",
    )

    if state_change is not None:
        expected_status = state_change.get(
            "expected"
        )
        actual_status = state_change.get(
            "actual"
        )

    if row["resource_type"] == "zfs_pool":
        display_name = row["pool_name"]
    else:
        display_name = (
            row["vdev_name"]
            or row["resource_key"]
        )

    notes = []

    if row["note"]:
        notes.append(row["note"])

    detail = changes_note(changes)

    if detail:
        notes.append(
            f"Observed differences: {detail}"
        )

    incident = {
        "resource_type":
            row["resource_type"],
        "resource_key":
            row["resource_key"],
        "display_name":
            display_name,
        "incident_type":
            row["incident_type"],
        "baseline_state":
            row["baseline_state"],
        "expected_status":
            expected_status,
        "actual_status":
            actual_status,
        "occurrence_count":
            row["occurrence_count"],
        "opened_at":
            row["opened_at"],
        "last_abnormal_at":
            row["last_abnormal_at"],
    }

    if notes:
        incident["note"] = " ".join(notes)

    return row, incident



def build_backup(db, incident_id):
    row = db.execute(
        """
        SELECT
            id,
            resource_type,
            resource_key,
            display_name,
            incident_type,
            incident_state,
            baseline_state,
            opened_at,
            last_abnormal_at,
            recovered_at,
            occurrence_count,
            latest_changes_json,
            note
        FROM backup_incidents
        WHERE id=?
        """,
        (incident_id,),
    ).fetchone()

    if row is None:
        raise PacketError(
            f"BACKUP incident {incident_id} not found"
        )

    changes = load_changes(
        row["latest_changes_json"]
    )

    expected_status = None
    actual_status = None

    if changes:
        first = changes[0]

        if isinstance(first, dict):
            field = first.get("field")
            expected = first.get("expected")
            actual = first.get("actual")

            if field:
                expected_status = (
                    f"{field}={expected!r}"
                )
                actual_status = (
                    f"{field}={actual!r}"
                )

    notes = []

    if row["note"]:
        notes.append(row["note"])

    detail = changes_note(changes)

    if detail:
        notes.append(
            f"Observed differences: {detail}"
        )

    incident = {
        "resource_type":
            row["resource_type"],
        "resource_key":
            row["resource_key"],
        "display_name":
            row["display_name"],
        "incident_type":
            row["incident_type"],
        "baseline_state":
            row["baseline_state"],
        "expected_status":
            expected_status,
        "actual_status":
            actual_status,
        "occurrence_count":
            row["occurrence_count"],
        "opened_at":
            row["opened_at"],
        "last_abnormal_at":
            row["last_abnormal_at"],
    }

    if notes:
        incident["note"] = " ".join(notes)

    return row, incident



def build_ha(db, incident_id):
    row = db.execute(
        """
        SELECT
            id,
            resource_type,
            resource_key,
            display_name,
            incident_type,
            incident_state,
            baseline_state,
            opened_at,
            last_abnormal_at,
            recovered_at,
            occurrence_count,
            latest_changes_json,
            note
        FROM ha_incidents
        WHERE id=?
        """,
        (incident_id,),
    ).fetchone()

    if row is None:
        raise PacketError(
            f"HA incident {incident_id} not found"
        )

    try:
        changes = json.loads(
            row["latest_changes_json"]
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise PacketError(
            f"invalid HA changes JSON: {exc}"
        ) from exc

    if not isinstance(changes, dict):
        raise PacketError(
            "HA changes JSON must be an object"
        )

    expected_status = changes.get(
        "expected_status"
    )

    actual_status = changes.get(
        "actual_status"
    )

    incident = {
        "resource_type":
            row["resource_type"],
        "resource_key":
            row["resource_key"],
        "display_name":
            row["display_name"],
        "incident_type":
            row["incident_type"],
        "baseline_state":
            row["baseline_state"],
        "expected_status":
            expected_status,
        "actual_status":
            actual_status,
        "occurrence_count":
            row["occurrence_count"],
        "opened_at":
            row["opened_at"],
        "last_abnormal_at":
            row["last_abnormal_at"],
    }

    if row["note"] is not None:
        incident["note"] = row["note"]

    return row, incident



def build_self(db, incident_id):
    row = db.execute(
        """
        SELECT
            id,
            signal_key,
            incident_type,
            severity,
            incident_state,
            detail_json,
            opened_at,
            recovered_at,
            last_seen_at
        FROM self_incidents
        WHERE id=?
        """,
        (incident_id,),
    ).fetchone()

    if row is None:
        raise PacketError(
            f"SELF incident {incident_id} not found"
        )

    detail = {}
    if row["detail_json"]:
        try:
            parsed = json.loads(row["detail_json"])
        except (
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise PacketError(
                f"invalid SELF detail JSON: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise PacketError(
                "SELF detail JSON must be an object"
            )
        detail = parsed

    display_name = row["signal_key"]
    incident = {
        "resource_type": "rackmarshal_self",
        "resource_key": row["signal_key"],
        "display_name": display_name,
        "incident_type": row["incident_type"],
        "baseline_state": None,
        "expected_status": "healthy",
        "actual_status": row["incident_type"],
        "occurrence_count": 1,
        "opened_at": row["opened_at"],
        "last_abnormal_at": row["last_seen_at"],
        "severity": row["severity"],
        "signal_key": row["signal_key"],
    }
    if detail:
        incident["detail"] = detail
        # optional human note from detail
        note_bits = []
        if "domain" in detail:
            note_bits.append(f"domain={detail['domain']}")
        if "unit" in detail:
            note_bits.append(f"unit={detail['unit']}")
        if "age_seconds" in detail:
            note_bits.append(
                f"age_seconds={detail['age_seconds']}"
            )
        if note_bits:
            incident["note"] = "; ".join(note_bits)

    return row, incident


def build_hardware(db, incident_id):
    """Build from hardware_incidents.id (ledger parity Step E)."""
    row = db.execute(
        """
        SELECT
            id,
            serial,
            role,
            model,
            incident_type,
            severity,
            incident_state,
            opened_at,
            last_abnormal_at,
            recovered_at,
            occurrence_count,
            opening_changes_json,
            latest_changes_json,
            note
        FROM hardware_incidents
        WHERE id=?
        """,
        (incident_id,),
    ).fetchone()
    if row is None:
        raise PacketError(
            f"HARDWARE incident {incident_id} not found"
        )

    detail = {}
    for key in ("latest_changes_json", "opening_changes_json"):
        raw = row[key]
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                detail.update(parsed)
        except (TypeError, json.JSONDecodeError):
            pass

    temp = detail.get("temperature_c")
    if temp is None:
        temp_text = "temperature unavailable"
    else:
        try:
            temp_text = f"{float(temp):.1f}C"
        except (TypeError, ValueError):
            temp_text = f"{temp}C"

    display_name = f"{row['role']} ({row['serial']})"
    severity = row["severity"]
    incident_state = row["incident_state"]
    note = row["note"] or (
        f"{row['incident_type']} severity={severity} at {temp_text}"
    )

    incident = {
        "resource_type": "hardware_temperature",
        "resource_key": row["serial"],
        "display_name": display_name,
        "incident_type": row["incident_type"],
        "baseline_state": None,
        "expected_status": "OK",
        "actual_status": severity,
        "occurrence_count": row["occurrence_count"],
        "opened_at": row["opened_at"],
        "last_abnormal_at": row["last_abnormal_at"],
        "recovered_at": row["recovered_at"],
        "severity": severity,
        "serial": row["serial"],
        "role": row["role"],
        "model": row["model"],
        "temperature_c": temp,
        "note": note,
    }

    class _Row(dict):
        def __getitem__(self, key):
            return dict.__getitem__(self, key)

    synthetic = _Row(
        {
            "id": row["id"],
            "incident_state": incident_state,
            "recovered_at": row["recovered_at"],
            "severity": severity,
            "serial": row["serial"],
            "role": row["role"],
            "temperature_c": temp,
            "observed_at": row["last_abnormal_at"] or row["opened_at"],
            "incident_type": row["incident_type"],
        }
    )
    return synthetic, incident



def build_mount(db, incident_id):
    row = db.execute(
        """
        SELECT
            id,
            mount_id,
            guest_kind,
            guest_id,
            mountpoint,
            display_name,
            incident_type,
            severity,
            incident_state,
            opened_at,
            last_abnormal_at,
            recovered_at,
            occurrence_count,
            latest_changes_json
        FROM mount_incidents
        WHERE id=?
        """,
        (incident_id,),
    ).fetchone()
    if row is None:
        raise PacketError(f"MOUNT incident {incident_id} not found")
    detail = {}
    if row["latest_changes_json"]:
        try:
            parsed = json.loads(row["latest_changes_json"])
            if isinstance(parsed, dict):
                detail = parsed
        except (TypeError, json.JSONDecodeError):
            detail = {}
    incident = {
        "resource_type": "mount",
        "resource_key": row["mount_id"],
        "display_name": row["display_name"],
        "incident_type": row["incident_type"],
        "baseline_state": None,
        "expected_status": "ok",
        "actual_status": row["incident_type"],
        "occurrence_count": row["occurrence_count"],
        "opened_at": row["opened_at"],
        "last_abnormal_at": row["last_abnormal_at"],
        "severity": row["severity"],
        "mount_id": row["mount_id"],
        "guest_kind": row["guest_kind"],
        "guest_id": row["guest_id"],
        "mountpoint": row["mountpoint"],
    }
    if detail:
        incident["detail"] = detail
        note_bits = []
        if detail.get("expected_source"):
            note_bits.append(f"expected={detail['expected_source']}")
        if detail.get("observed_source"):
            note_bits.append(f"observed={detail['observed_source']}")
        if detail.get("detail"):
            note_bits.append(str(detail["detail"]))
        if note_bits:
            incident["note"] = "; ".join(note_bits)
    return row, incident


def build_packet(
    db,
    source_domain,
    incident_id,
    notification_type,
):
    if source_domain == "PVE":
        row, incident = build_pve(
            db,
            incident_id,
        )

    elif source_domain == "ZFS":
        row, incident = build_zfs(
            db,
            incident_id,
        )

    elif source_domain == "BACKUP":
        row, incident = build_backup(
            db,
            incident_id,
        )

    elif source_domain == "HA":
        row, incident = build_ha(
            db,
            incident_id,
        )

    elif source_domain == "SELF":
        row, incident = build_self(
            db,
            incident_id,
        )

    elif source_domain == "HARDWARE":
        row, incident = build_hardware(
            db,
            incident_id,
        )

    elif source_domain == "MOUNT":
        row, incident = build_mount(
            db,
            incident_id,
        )


    else:
        raise PacketError(
            f"unsupported source_domain: "
            f"{source_domain}"
        )

    if notification_type == "OPENED":
        if row["incident_state"] != "OPEN":
            raise PacketError(
                "OPENED packet requires "
                "OPEN incident"
            )

    elif notification_type == "RECOVERED":
        if row["incident_state"] != "RECOVERED":
            raise PacketError(
                "RECOVERED packet requires "
                "RECOVERED incident"
            )

        if row["recovered_at"] is None:
            raise PacketError(
                "RECOVERED incident has no "
                "recovered_at"
            )

    else:
        raise PacketError(
            f"unsupported notification_type: "
            f"{notification_type}"
        )

    packet = {
        "schema_version": SCHEMA_VERSION,
        "builder": BUILDER,
        "source_domain": source_domain,
        "incident_id": incident_id,
        "notification_type":
            notification_type,
        "incident": incident,
    }

    if notification_type == "RECOVERED":
        packet["recovery"] = {
            "recovered_at":
                row["recovered_at"],
        }

    return packet


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic RackMarshal "
            "incident notification packet."
        )
    )

    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
    )

    parser.add_argument(
        "--domain",
        required=True,
        choices=(
            "PVE",
            "ZFS",
            "BACKUP",
            "HA",
            "SELF",
            "HARDWARE",
            "MOUNT",
        ),
    )

    parser.add_argument(
        "--incident-id",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--notification-type",
        required=True,
        choices=(
            "OPENED",
            "RECOVERED",
        ),
    )

    args = parser.parse_args()

    try:
        db = sqlite3.connect(
            f"file:{args.db}?mode=ro",
            uri=True,
        )
        db.row_factory = sqlite3.Row

        try:
            packet = build_packet(
                db,
                args.domain,
                args.incident_id,
                args.notification_type,
            )
        finally:
            db.close()

    except (
        PacketError,
        sqlite3.Error,
    ) as exc:
        print(
            json.dumps(
                {
                    "schema_version":
                        SCHEMA_VERSION,
                    "builder":
                        BUILDER,
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
            packet,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
