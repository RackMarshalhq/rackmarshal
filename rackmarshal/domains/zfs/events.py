#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from rackmarshal.core.config import state_db


DEFAULT_DB = state_db()

VALID_OUTCOMES = {
    "STATUS-CHANGED",
    "COUNTER-CHANGED",
    "MISSING",
    "NEW",
}

VALID_RESOURCE_TYPES = {
    "zfs_pool",
    "zfs_vdev",
}

VALID_BASELINE_STATES = {
    "VERIFIED",
    "EXPECTED",
    "KNOWN-ISSUE",
    "FAILED",
    "DECOMMISSIONED",
}


def fail(message):
    print(
        json.dumps(
            {
                "recorder": "zfs_events",
                "status": "ERROR",
                "error": message,
            },
            sort_keys=True,
        )
    )
    raise SystemExit(1)


def load_input():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON input: {exc}")

    if not isinstance(payload, dict):
        fail("input must be a JSON object")

    return payload


def validate_comparator(payload):
    if payload.get("comparator") != "zfs_baseline":
        fail("unexpected comparator")

    observation_id = payload.get("observation_id")

    if (
        isinstance(observation_id, bool)
        or not isinstance(observation_id, int)
        or observation_id < 1
    ):
        fail("invalid observation_id")

    observed_at = payload.get("observed_at")

    if (
        not isinstance(observed_at, str)
        or not observed_at.strip()
    ):
        fail("invalid observed_at")

    results = payload.get("results")

    if not isinstance(results, list):
        fail("results must be a list")

    return observation_id, observed_at, results


def normalize_event(
    result,
    observation_id,
    observed_at,
):
    if not isinstance(result, dict):
        fail("each result must be an object")

    outcome = result.get("outcome")

    if outcome == "MATCH":
        return None

    if outcome not in VALID_OUTCOMES:
        fail(f"invalid outcome: {outcome!r}")

    resource_type = result.get("resource_type")

    if resource_type not in VALID_RESOURCE_TYPES:
        fail(
            f"invalid resource_type: "
            f"{resource_type!r}"
        )

    resource_key = result.get("resource_key")

    if (
        not isinstance(resource_key, str)
        or not resource_key.strip()
    ):
        fail("invalid resource_key")

    baseline_state = result.get(
        "baseline_state"
    )

    if (
        baseline_state is not None
        and baseline_state
        not in VALID_BASELINE_STATES
    ):
        fail(
            f"invalid baseline_state: "
            f"{baseline_state!r}"
        )

    changes = result.get("changes", [])

    if not isinstance(changes, list):
        fail("changes must be a list")

    if resource_type == "zfs_pool":
        pool_name = resource_key
        vdev_name = None
    else:
        pool_name = result.get("pool_name")
        vdev_name = result.get("vdev_name")

        if (
            not isinstance(pool_name, str)
            or not pool_name.strip()
        ):
            fail(
                "zfs_vdev result missing "
                "pool_name"
            )

        if (
            not isinstance(vdev_name, str)
            or not vdev_name.strip()
        ):
            fail(
                "zfs_vdev result missing "
                "vdev_name"
            )

    return {
        "observation_id": observation_id,
        "resource_type": resource_type,
        "resource_key": resource_key,
        "pool_name": pool_name,
        "vdev_name": vdev_name,
        "outcome": outcome,
        "baseline_state": baseline_state,
        "changes_json": json.dumps(
            changes,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "observed_at": observed_at,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB,
        help=(
            "SQLite database path "
            "(default: configured STATE_DB)"
        ),
    )

    args = parser.parse_args()

    payload = load_input()

    (
        observation_id,
        observed_at,
        results,
    ) = validate_comparator(payload)

    events = []

    for result in results:
        event = normalize_event(
            result,
            observation_id,
            observed_at,
        )

        if event is not None:
            events.append(event)

    try:
        conn = sqlite3.connect(
            str(args.database)
        )

        conn.execute(
            "PRAGMA foreign_keys = ON"
        )

        conn.execute("BEGIN IMMEDIATE")

        inserted = 0
        duplicates = 0

        for event in events:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO zfs_events (
                    observation_id,
                    resource_type,
                    resource_key,
                    pool_name,
                    vdev_name,
                    outcome,
                    baseline_state,
                    changes_json,
                    observed_at
                )
                VALUES (
                    :observation_id,
                    :resource_type,
                    :resource_key,
                    :pool_name,
                    :vdev_name,
                    :outcome,
                    :baseline_state,
                    :changes_json,
                    :observed_at
                )
                """,
                event,
            )

            if cursor.rowcount == 1:
                inserted += 1
            else:
                duplicates += 1

        conn.commit()

    except sqlite3.Error as exc:
        try:
            conn.rollback()
        except Exception:
            pass

        fail(
            f"database write failed: {exc}"
        )

    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(
        json.dumps(
            {
                "recorder": "zfs_events",
                "observation_id":
                    observation_id,
                "candidate_events":
                    len(events),
                "inserted":
                    inserted,
                "duplicates":
                    duplicates,
                "status": "OK",
            },
            indent=4,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
