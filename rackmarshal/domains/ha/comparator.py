#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys

from rackmarshal.core.config import state_db

DB_DEFAULT = str(state_db())
COLLECTOR = "home_assistant"


def load_observation(conn, observation_id=None):
    if observation_id is None:
        row = conn.execute("""
            SELECT id, observed_at, payload_json
            FROM observations
            WHERE collector = ?
            ORDER BY id DESC
            LIMIT 1
        """, (COLLECTOR,)).fetchone()
    else:
        row = conn.execute("""
            SELECT id, observed_at, payload_json
            FROM observations
            WHERE id = ?
              AND collector = ?
        """, (observation_id, COLLECTOR)).fetchone()

    if row is None:
        raise RuntimeError("No matching Home Assistant observation found")

    obs_id, observed_at, payload_json = row

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Observation {obs_id} contains invalid JSON: {exc}"
        ) from exc

    return obs_id, observed_at, payload


def load_baseline(conn):
    rows = conn.execute("""
        SELECT
            resource_key,
            resource_type,
            display_name,
            baseline_state,
            expected_status,
            source_observation_id
        FROM ha_resource_baseline
        ORDER BY resource_key
    """).fetchall()

    if not rows:
        raise RuntimeError("Home Assistant baseline is empty")

    return {
        row[0]: {
            "resource_key": row[0],
            "resource_type": row[1],
            "display_name": row[2],
            "baseline_state": row[3],
            "expected_status": row[4],
            "source_observation_id": row[5],
        }
        for row in rows
    }


def compare(baseline, payload):
    observed_resources = payload.get("resources")

    if not isinstance(observed_resources, list):
        raise RuntimeError(
            "Home Assistant payload does not contain a resources list"
        )

    observed = {}

    for resource in observed_resources:
        key = resource.get("resource_key")

        if not key:
            raise RuntimeError(
                "Observed Home Assistant resource missing resource_key"
            )

        if key in observed:
            raise RuntimeError(
                f"Duplicate observed resource_key: {key}"
            )

        observed[key] = resource

    results = []

    # Baseline resources: MATCH, STATUS-CHANGED, or MISSING.
    for key in sorted(baseline):
        expected = baseline[key]
        actual = observed.get(key)

        if actual is None:
            results.append({
                "outcome": "MISSING",
                "resource_key": key,
                "resource_type": expected["resource_type"],
                "display_name": expected["display_name"],
                "baseline_state": expected["baseline_state"],
                "expected_status": expected["expected_status"],
                "actual_status": None,
            })
            continue

        actual_type = actual.get("resource_type")
        actual_status = actual.get("status")

        # Resource identity/type drift is abnormal even if status text matches.
        if (
            actual_type != expected["resource_type"]
            or actual_status != expected["expected_status"]
        ):
            results.append({
                "outcome": "STATUS-CHANGED",
                "resource_key": key,
                "resource_type": actual_type,
                "display_name": actual.get(
                    "display_name",
                    expected["display_name"],
                ),
                "baseline_state": expected["baseline_state"],
                "expected_resource_type": expected["resource_type"],
                "actual_resource_type": actual_type,
                "expected_status": expected["expected_status"],
                "actual_status": actual_status,
            })
        else:
            results.append({
                "outcome": "MATCH",
                "resource_key": key,
                "resource_type": actual_type,
                "display_name": actual.get(
                    "display_name",
                    expected["display_name"],
                ),
                "baseline_state": expected["baseline_state"],
                "expected_status": expected["expected_status"],
                "actual_status": actual_status,
            })

    # Observed resources absent from baseline are NEW.
    for key in sorted(set(observed) - set(baseline)):
        actual = observed[key]

        results.append({
            "outcome": "NEW",
            "resource_key": key,
            "resource_type": actual.get("resource_type"),
            "display_name": actual.get("display_name", key),
            "baseline_state": None,
            "expected_status": None,
            "actual_status": actual.get("status"),
        })

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default=DB_DEFAULT,
        help="SQLite state database",
    )
    parser.add_argument(
        "--observation-id",
        type=int,
        default=None,
        help="Specific home_assistant observation to compare",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)

    try:
        baseline = load_baseline(conn)
        obs_id, observed_at, payload = load_observation(
            conn,
            args.observation_id,
        )
        results = compare(baseline, payload)
    finally:
        conn.close()

    counts = {}
    for result in results:
        outcome = result["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1

    output = {
        "collector": COLLECTOR,
        "observation_id": obs_id,
        "observed_at": observed_at,
        "baseline_resources": len(baseline),
        "observed_resources": len(payload.get("resources", [])),
        "result_count": len(results),
        "counts": {
            "MATCH": counts.get("MATCH", 0),
            "STATUS-CHANGED": counts.get("STATUS-CHANGED", 0),
            "MISSING": counts.get("MISSING", 0),
            "NEW": counts.get("NEW", 0),
        },
        "differences": sum(
            count
            for outcome, count in counts.items()
            if outcome != "MATCH"
        ),
        "results": results,
    }

    print(json.dumps(output, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
