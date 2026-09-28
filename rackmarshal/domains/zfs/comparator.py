#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from rackmarshal.core.config import state_db


DB_PATH = state_db()


def fail(message, rc=1):
    print(
        json.dumps(
            {
                "schema_version": 1,
                "comparator": "zfs_baseline",
                "error": message,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    raise SystemExit(rc)


def flatten_vdevs(pool_name, vdevs):
    result = {}

    def visit(vdev):
        if not isinstance(vdev, dict):
            fail(
                f"pool {pool_name} contains invalid vdev"
            )

        name = vdev.get("name")

        if not isinstance(name, str) or not name:
            fail(
                f"pool {pool_name} contains unnamed vdev"
            )

        key = (pool_name, name)

        if key in result:
            fail(
                f"duplicate vdev {pool_name}/{name}"
            )

        result[key] = vdev

        children = vdev.get("children", [])

        if not isinstance(children, list):
            fail(
                f"vdev {pool_name}/{name} "
                "has invalid children"
            )

        for child in children:
            visit(child)

    for vdev in vdevs:
        visit(vdev)

    return result


def pool_match_result(
    baseline,
    observed,
):
    name = baseline["pool_name"]

    status_changes = []
    counter_changes = []

    if str(observed.get("pool_guid")) != baseline["pool_guid"]:
        status_changes.append(
            {
                "field": "pool_guid",
                "expected": baseline["pool_guid"],
                "actual": str(observed.get("pool_guid")),
            }
        )

    if observed.get("state") != baseline["expected_state"]:
        status_changes.append(
            {
                "field": "state",
                "expected": baseline["expected_state"],
                "actual": observed.get("state"),
            }
        )

    actual_errors = observed.get("error_count")

    if actual_errors != baseline["expected_error_count"]:
        counter_changes.append(
            {
                "field": "error_count",
                "expected": baseline[
                    "expected_error_count"
                ],
                "actual": actual_errors,
            }
        )

    changes = status_changes + counter_changes

    if status_changes:
        outcome = "STATUS-CHANGED"
    elif counter_changes:
        outcome = "COUNTER-CHANGED"
    else:
        outcome = "MATCH"

    return {
        "resource_type": "zfs_pool",
        "resource_key": name,
        "baseline_state": baseline["baseline_state"],
        "outcome": outcome,
        "changes": changes,
    }


def vdev_match_result(
    baseline,
    observed,
):
    pool_name = baseline["pool_name"]
    vdev_name = baseline["vdev_name"]
    key = f"{pool_name}/{vdev_name}"

    status_changes = []
    counter_changes = []

    if observed.get("type") != baseline["vdev_type"]:
        status_changes.append(
            {
                "field": "type",
                "expected": baseline["vdev_type"],
                "actual": observed.get("type"),
            }
        )

    if observed.get("state") != baseline["expected_state"]:
        status_changes.append(
            {
                "field": "state",
                "expected": baseline["expected_state"],
                "actual": observed.get("state"),
            }
        )

    counter_fields = (
        ("read_errors", "expected_read_errors"),
        ("write_errors", "expected_write_errors"),
        (
            "checksum_errors",
            "expected_checksum_errors",
        ),
        ("slow_ios", "expected_slow_ios"),
    )

    for observed_field, baseline_field in counter_fields:
        expected = baseline[baseline_field]
        actual = observed.get(observed_field)

        if actual != expected:
            counter_changes.append(
                {
                    "field": observed_field,
                    "expected": expected,
                    "actual": actual,
                }
            )

    changes = status_changes + counter_changes

    if status_changes:
        outcome = "STATUS-CHANGED"
    elif counter_changes:
        outcome = "COUNTER-CHANGED"
    else:
        outcome = "MATCH"

    return {
        "resource_type": "zfs_vdev",
        "resource_key": key,
        "pool_name": pool_name,
        "vdev_name": vdev_name,
        "baseline_state": baseline["baseline_state"],
        "outcome": outcome,
        "changes": changes,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--observation-id",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DB_PATH,
        help=(
            "SQLite database path "
            "(default: configured STATE_DB)"
        ),
    )

    args = parser.parse_args()

    if args.observation_id < 1:
        fail("observation id must be positive")

    try:
        connection = sqlite3.connect(
            f"file:{args.database}?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        fail(f"unable to open database read-only: {exc}")

    try:
        observation = connection.execute(
            """
            SELECT
                id,
                observed_at,
                payload_json
            FROM zfs_observations
            WHERE id = ?
            """,
            (args.observation_id,),
        ).fetchone()

        if observation is None:
            fail(
                f"ZFS observation "
                f"{args.observation_id} not found"
            )

        pool_baseline_rows = connection.execute(
            """
            SELECT
                pool_name,
                pool_guid,
                baseline_state,
                expected_state,
                expected_error_count
            FROM zfs_pool_baseline
            ORDER BY pool_name
            """
        ).fetchall()

        vdev_baseline_rows = connection.execute(
            """
            SELECT
                pool_name,
                vdev_name,
                vdev_type,
                baseline_state,
                expected_state,
                expected_read_errors,
                expected_write_errors,
                expected_checksum_errors,
                expected_slow_ios
            FROM zfs_vdev_baseline
            ORDER BY pool_name, vdev_name
            """
        ).fetchall()

    except sqlite3.Error as exc:
        fail(f"database read failed: {exc}")

    finally:
        connection.close()

    try:
        payload = json.loads(
            observation["payload_json"]
        )
    except json.JSONDecodeError as exc:
        fail(
            "stored ZFS observation contains "
            f"invalid JSON: {exc}"
        )

    observed_pool_list = payload.get("pools")

    if not isinstance(observed_pool_list, list):
        fail("stored observation has invalid pools")

    observed_pools = {}

    observed_vdevs = {}

    for pool in observed_pool_list:
        if not isinstance(pool, dict):
            fail("stored observation contains invalid pool")

        name = pool.get("name")

        if not isinstance(name, str) or not name:
            fail("stored observation contains unnamed pool")

        if name in observed_pools:
            fail(f"duplicate observed pool: {name}")

        observed_pools[name] = pool

        pool_vdevs = pool.get("vdevs", [])

        if not isinstance(pool_vdevs, list):
            fail(
                f"pool {name} has invalid vdevs"
            )

        observed_vdevs.update(
            flatten_vdevs(name, pool_vdevs)
        )

    baseline_pools = {
        row["pool_name"]: dict(row)
        for row in pool_baseline_rows
    }

    baseline_vdevs = {
        (row["pool_name"], row["vdev_name"]): dict(row)
        for row in vdev_baseline_rows
    }

    results = []

    #
    # Baseline pools.
    #
    for pool_name in sorted(baseline_pools):
        baseline = baseline_pools[pool_name]
        observed = observed_pools.get(pool_name)

        if observed is None:
            results.append(
                {
                    "resource_type": "zfs_pool",
                    "resource_key": pool_name,
                    "baseline_state": baseline[
                        "baseline_state"
                    ],
                    "outcome": "MISSING",
                    "changes": [],
                }
            )
            continue

        results.append(
            pool_match_result(
                baseline,
                observed,
            )
        )

    #
    # Newly observed pools.
    #
    for pool_name in sorted(
        set(observed_pools) - set(baseline_pools)
    ):
        observed = observed_pools[pool_name]

        results.append(
            {
                "resource_type": "zfs_pool",
                "resource_key": pool_name,
                "baseline_state": None,
                "outcome": "NEW",
                "changes": [],
                "observed_state": observed.get("state"),
                "observed_error_count": observed.get(
                    "error_count"
                ),
                "observed_pool_guid": str(
                    observed.get("pool_guid")
                ),
            }
        )

    #
    # Baseline vdevs.
    #
    for key in sorted(baseline_vdevs):
        baseline = baseline_vdevs[key]
        observed = observed_vdevs.get(key)

        pool_name, vdev_name = key
        resource_key = f"{pool_name}/{vdev_name}"

        if observed is None:
            results.append(
                {
                    "resource_type": "zfs_vdev",
                    "resource_key": resource_key,
                    "pool_name": pool_name,
                    "vdev_name": vdev_name,
                    "baseline_state": baseline[
                        "baseline_state"
                    ],
                    "outcome": "MISSING",
                    "changes": [],
                }
            )
            continue

        results.append(
            vdev_match_result(
                baseline,
                observed,
            )
        )

    #
    # Newly observed vdevs.
    #
    for key in sorted(
        set(observed_vdevs) - set(baseline_vdevs)
    ):
        pool_name, vdev_name = key
        observed = observed_vdevs[key]

        results.append(
            {
                "resource_type": "zfs_vdev",
                "resource_key": (
                    f"{pool_name}/{vdev_name}"
                ),
                "pool_name": pool_name,
                "vdev_name": vdev_name,
                "baseline_state": None,
                "outcome": "NEW",
                "changes": [],
                "observed_type": observed.get("type"),
                "observed_state": observed.get("state"),
            }
        )

    counts = {
        "MATCH": 0,
        "STATUS-CHANGED": 0,
        "COUNTER-CHANGED": 0,
        "MISSING": 0,
        "NEW": 0,
    }

    for result in results:
        outcome = result["outcome"]

        if outcome not in counts:
            fail(f"unexpected outcome: {outcome}")

        counts[outcome] += 1

    output = {
        "schema_version": 1,
        "comparator": "zfs_baseline",
        "observation_id": observation["id"],
        "observed_at": observation["observed_at"],
        "result_count": len(results),
        "counts": counts,
        "results": results,
    }

    print(
        json.dumps(
            output,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
