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
    "MISSING",
    "NEW",
}

VALID_RESOURCE_TYPES = {
    "backup_job",
    "backup_guest",
    "backup_scheduled_run",
    "backup_timemachine",
    "backup_phone",
    "backup_messages",
    "backup_host_verify",
    "backup_rsync_filebackups",
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
                "schema_version": 1,
                "recorder": "backup_events",
                "status": "ERROR",
                "error": message,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
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
    if payload.get("schema_version") != 1:
        fail("unsupported comparator schema")

    if payload.get("comparator") != "backup_baseline":
        fail("unexpected comparator")

    observation_id = payload.get("observation_id")

    if (
        isinstance(observation_id, bool)
        or not isinstance(observation_id, int)
        or observation_id < 1
    ):
        fail("invalid observation_id")

    observed_at = payload.get("observed_at")

    if not isinstance(observed_at, str) or not observed_at:
        fail("invalid observed_at")

    results = payload.get("results")

    if not isinstance(results, list):
        fail("results must be a list")

    return observation_id, observed_at, results


def normalize_event(result, observation_id, observed_at):
    if not isinstance(result, dict):
        fail("each result must be an object")

    outcome = result.get("outcome")

    if outcome == "MATCH":
        return None

    if outcome not in VALID_OUTCOMES:
        fail(f"invalid outcome: {outcome!r}")

    resource_type = result.get("resource_type")

    if resource_type not in VALID_RESOURCE_TYPES:
        fail(f"invalid resource_type: {resource_type!r}")

    resource_key = result.get("resource_key")

    if not isinstance(resource_key, str) or not resource_key:
        fail("invalid resource_key")

    baseline_state = result.get("baseline_state")

    if (
        baseline_state is not None
        and baseline_state not in VALID_BASELINE_STATES
    ):
        fail(f"invalid baseline_state: {baseline_state!r}")

    changes = result.get("changes", [])

    if not isinstance(changes, list):
        fail("changes must be a list")

    return {
        "observation_id": observation_id,
        "resource_type": resource_type,
        "resource_key": resource_key,
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
    )

    args = parser.parse_args()

    payload = load_input()

    observation_id, observed_at, results = validate_comparator(
        payload
    )

    events = []

    seen = set()

    for result in results:
        event = normalize_event(
            result,
            observation_id,
            observed_at,
        )

        if event is None:
            continue

        identity = (
            event["resource_type"],
            event["resource_key"],
            event["outcome"],
        )

        if identity in seen:
            fail(f"duplicate comparator event {identity!r}")

        seen.add(identity)
        events.append(event)

    try:
        conn = sqlite3.connect(str(args.database))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")

        observation = conn.execute(
            """
            SELECT collector, observed_at
            FROM observations
            WHERE id = ?
            """,
            (observation_id,),
        ).fetchone()

        if observation is None:
            fail(
                f"observation {observation_id} does not exist"
            )

        if observation[0] != "backup_domain":
            fail(
                f"observation {observation_id} "
                "is not backup_domain"
            )

        if observation[1] != observed_at:
            fail(
                "comparator observed_at does not match "
                "stored observation"
            )

        inserted = 0
        duplicates = 0

        for event in events:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO backup_events (
                    observation_id,
                    resource_type,
                    resource_key,
                    outcome,
                    baseline_state,
                    changes_json,
                    observed_at
                )
                VALUES (
                    :observation_id,
                    :resource_type,
                    :resource_key,
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

        fail(f"database write failed: {exc}")

    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(
        json.dumps(
            {
                "schema_version": 1,
                "recorder": "backup_events",
                "observation_id": observation_id,
                "candidate_events": len(events),
                "inserted": inserted,
                "duplicates": duplicates,
                "status": "OK",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
