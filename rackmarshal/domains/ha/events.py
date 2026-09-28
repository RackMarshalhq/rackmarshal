#!/usr/bin/env python3

import argparse
import json
import sqlite3
import subprocess
import sys

from rackmarshal.core.config import install_root, state_db

# Phase 2 Step 14: derive COMPARATOR_DEFAULT from config helpers
# (defaults = today's layout).
DB_DEFAULT = str(state_db())
COMPARATOR_DEFAULT = [sys.executable, "-m", "rackmarshal.domains.ha.comparator"]

EVENT_OUTCOMES = {
    "STATUS-CHANGED",
    "MISSING",
    "NEW",
}


def run_comparator(comparator, db, observation_id=None):
    cmd = (list(comparator) if isinstance(comparator, (list, tuple)) else [comparator]) + [
        "--db",
        db,
    ]

    if observation_id is not None:
        cmd += [
            "--observation-id",
            str(observation_id),
        ]

    result = subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
    )

    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db",
        default=DB_DEFAULT,
    )

    parser.add_argument(
        "--comparator",
        default=None,
    )

    parser.add_argument(
        "--observation-id",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    comparison = run_comparator(
        args.comparator or COMPARATOR_DEFAULT,
        args.db,
        args.observation_id,
    )

    observation_id = comparison["observation_id"]
    observed_at = comparison["observed_at"]

    inserted = 0
    existing = 0

    conn = sqlite3.connect(args.db)

    try:
        conn.execute("PRAGMA foreign_keys=ON")

        for result in comparison["results"]:
            outcome = result["outcome"]

            if outcome not in EVENT_OUTCOMES:
                continue

            changes = {}

            if outcome == "STATUS-CHANGED":
                changes = {
                    "expected_resource_type":
                        result.get("expected_resource_type"),
                    "actual_resource_type":
                        result.get("actual_resource_type"),
                    "expected_status":
                        result.get("expected_status"),
                    "actual_status":
                        result.get("actual_status"),
                }

            elif outcome == "MISSING":
                changes = {
                    "expected_status":
                        result.get("expected_status"),
                    "actual_status": None,
                }

            elif outcome == "NEW":
                changes = {
                    "expected_status": None,
                    "actual_status":
                        result.get("actual_status"),
                }

            before = conn.total_changes

            conn.execute("""
                INSERT OR IGNORE INTO ha_events (
                    observation_id,
                    resource_type,
                    resource_key,
                    outcome,
                    baseline_state,
                    changes_json,
                    observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                observation_id,
                result["resource_type"],
                result["resource_key"],
                outcome,
                result.get("baseline_state"),
                json.dumps(
                    changes,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                observed_at,
            ))

            if conn.total_changes > before:
                inserted += 1
            else:
                existing += 1

        conn.commit()

    finally:
        conn.close()

    output = {
        "collector": "home_assistant",
        "observation_id": observation_id,
        "differences": comparison["differences"],
        "events_inserted": inserted,
        "events_existing": existing,
    }

    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
