#!/usr/bin/env python3

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from rackmarshal.core.config import install_root, state_db, venv_python

# Phase 2 Step 13: derive PYTHON/COMPARATOR from config helpers
# (defaults = today's layout).
DB_FILE = state_db()
_ROOT = install_root()
PYTHON = str(venv_python())
COMPARATOR = [PYTHON, "-m", "rackmarshal.domains.pve.comparator"]

ALLOWED_EVENT_TYPES = {
    "STATUS-CHANGED",
    "MISSING",
    "NEW",
}

ALLOWED_BASELINE_STATES = {
    "VERIFIED",
    "EXPECTED",
    "KNOWN-ISSUE",
    "FAILED",
    "DECOMMISSIONED",
}


class EventRecorderError(Exception):
    pass


def run_comparator(observation_id):
    result = subprocess.run(
        COMPARATOR + [
            "--observation-id",
            str(observation_id),
        ],
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()

        raise EventRecorderError(
            "comparator failed"
            + (f": {stderr}" if stderr else "")
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EventRecorderError(
            "comparator returned invalid JSON"
        ) from exc

    return data


def validate_comparison(data, observation_id):
    if not isinstance(data, dict):
        raise EventRecorderError(
            "comparison output is not a JSON object"
        )

    if data.get("schema_version") != 1:
        raise EventRecorderError(
            "unsupported comparator schema version"
        )

    if data.get("comparator") != "pve_resource_baseline":
        raise EventRecorderError(
            "unexpected comparator identity"
        )

    if data.get("observation_id") != observation_id:
        raise EventRecorderError(
            "comparator observation ID does not match request"
        )

    differences = data.get("differences")

    if not isinstance(differences, list):
        raise EventRecorderError(
            "comparison differences is not an array"
        )

    summary = data.get("summary")

    if not isinstance(summary, dict):
        raise EventRecorderError(
            "comparison summary is not an object"
        )

    expected_difference_count = sum(
        summary.get(key, 0)
        for key in (
            "STATUS-CHANGED",
            "MISSING",
            "NEW",
        )
    )

    if len(differences) != expected_difference_count:
        raise EventRecorderError(
            "difference count does not match comparator summary"
        )

    validated = []

    seen = set()

    for difference in differences:
        if not isinstance(difference, dict):
            raise EventRecorderError(
                "difference entry is not an object"
            )

        event_type = difference.get("result")
        resource_type = difference.get("resource_type")
        resource_key = difference.get("resource_key")
        baseline_state = difference.get("baseline_state")

        if event_type not in ALLOWED_EVENT_TYPES:
            raise EventRecorderError(
                f"unsupported event type: {event_type!r}"
            )

        if not isinstance(resource_type, str) or not resource_type:
            raise EventRecorderError(
                "difference has invalid resource_type"
            )

        if not isinstance(resource_key, str) or not resource_key:
            raise EventRecorderError(
                "difference has invalid resource_key"
            )

        if (
            baseline_state is not None
            and baseline_state not in ALLOWED_BASELINE_STATES
        ):
            raise EventRecorderError(
                f"invalid baseline state: {baseline_state!r}"
            )

        identity = (
            event_type,
            resource_type,
            resource_key,
        )

        if identity in seen:
            raise EventRecorderError(
                f"duplicate comparator difference: {identity}"
            )

        seen.add(identity)

        validated.append({
            "event_type": event_type,
            "resource_type": resource_type,
            "resource_key": resource_key,
            "display_name": difference.get("display_name"),
            "baseline_state": baseline_state,
            "expected_status": difference.get("expected_status"),
            "actual_status": difference.get("actual_status"),
            "note": difference.get("note"),
        })

    return validated


def record_events(observation_id, events):
    connection = sqlite3.connect(DB_FILE)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        exists = connection.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE id = ?
            """,
            (observation_id,),
        ).fetchone()[0]

        if exists != 1:
            raise EventRecorderError(
                f"observation {observation_id} does not exist"
            )

        connection.execute("BEGIN IMMEDIATE")

        before = connection.total_changes

        for event in events:
            connection.execute(
                """
                INSERT OR IGNORE INTO resource_events (
                    observation_id,
                    event_type,
                    resource_type,
                    resource_key,
                    display_name,
                    baseline_state,
                    expected_status,
                    actual_status,
                    note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    event["event_type"],
                    event["resource_type"],
                    event["resource_key"],
                    event["display_name"],
                    event["baseline_state"],
                    event["expected_status"],
                    event["actual_status"],
                    event["note"],
                ),
            )

        inserted = connection.total_changes - before

        connection.commit()

        return inserted

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Record deterministic RackMarshal resource events "
            "from a stored PVE observation."
        )
    )

    parser.add_argument(
        "--observation-id",
        type=int,
        required=True,
        help="Stored observation ID to evaluate.",
    )

    args = parser.parse_args()

    if args.observation_id <= 0:
        print(
            "EVENT RECORDER ERROR: observation ID must be positive",
            file=sys.stderr,
        )
        return 2

    try:
        comparison = run_comparator(
            args.observation_id
        )

        events = validate_comparison(
            comparison,
            args.observation_id,
        )

        inserted = record_events(
            args.observation_id,
            events,
        )

    except (
        EventRecorderError,
        sqlite3.Error,
        OSError,
    ) as exc:
        print(
            f"EVENT RECORDER ERROR: {exc}",
            file=sys.stderr,
        )
        return 2

    output = {
        "schema_version": 1,
        "recorder": "pve_resource_events",
        "observation_id": args.observation_id,
        "differences_detected": len(events),
        "events_inserted": inserted,
        "events_already_recorded": (
            len(events) - inserted
        ),
    }

    print(
        json.dumps(
            output,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
