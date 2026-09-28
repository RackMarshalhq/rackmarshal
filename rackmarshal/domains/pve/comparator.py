#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from rackmarshal.core.config import state_db


DB_FILE = state_db()


class CompareError(Exception):
    pass


def resource_identity(resource):
    resource_type = resource.get("type")

    if resource_type in ("lxc", "qemu"):
        vmid = resource.get("vmid")

        if vmid is None:
            raise CompareError(
                f"{resource_type} resource is missing vmid"
            )

        return resource_type, str(vmid)

    if resource_type == "storage":
        storage = resource.get("storage")

        if not storage:
            raise CompareError(
                "storage resource is missing storage name"
            )

        return "storage", str(storage)

    if resource_type in ("node", "network"):
        node = resource.get("node")

        if not node:
            raise CompareError(
                f"{resource_type} resource is missing node"
            )

        return resource_type, str(node)

    raise CompareError(
        f"unsupported resource type: {resource_type!r}"
    )


def current_display_name(resource):
    resource_type = resource["type"]

    if resource_type in ("lxc", "qemu"):
        return resource.get("name")

    if resource_type == "storage":
        return resource.get("storage")

    if resource_type == "node":
        return resource.get("node")

    if resource_type == "network":
        node = resource.get("node")
        return f"{node} network" if node else None

    return None


def load_observation(connection, observation_id):
    row = connection.execute(
        """
        SELECT
            id,
            observed_at,
            payload_json
        FROM observations
        WHERE id = ?
        """,
        (observation_id,),
    ).fetchone()

    if row is None:
        raise CompareError(
            f"observation {observation_id} does not exist"
        )

    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError as exc:
        raise CompareError(
            f"observation {observation_id} contains invalid JSON"
        ) from exc

    resources = payload.get("resources")

    if not isinstance(resources, list):
        raise CompareError(
            f"observation {observation_id} has no valid resources array"
        )

    return row, payload, resources


def load_baseline(connection):
    rows = connection.execute(
        """
        SELECT
            resource_type,
            resource_key,
            display_name,
            expected_status,
            baseline_state,
            note
        FROM resource_baseline
        ORDER BY resource_type, resource_key
        """
    ).fetchall()

    if not rows:
        raise CompareError("resource baseline is empty")

    baseline = {}

    for row in rows:
        key = (
            row["resource_type"],
            row["resource_key"],
        )

        if key in baseline:
            raise CompareError(
                f"duplicate baseline identity: {key}"
            )

        baseline[key] = row

    return baseline


def compare(resources, baseline):
    current = {}

    for resource in resources:
        identity = resource_identity(resource)

        if identity in current:
            raise CompareError(
                f"duplicate resource in observation: {identity}"
            )

        current[identity] = resource

    results = []

    all_identities = sorted(
        set(baseline) | set(current),
        key=lambda item: (item[0], item[1]),
    )

    for identity in all_identities:
        baseline_row = baseline.get(identity)
        resource = current.get(identity)

        resource_type, resource_key = identity

        if baseline_row is None:
            results.append({
                "result": "NEW",
                "resource_type": resource_type,
                "resource_key": resource_key,
                "display_name": current_display_name(resource),
                "expected_status": None,
                "actual_status": resource.get("status"),
                "baseline_state": None,
                "note": "Resource exists in observation but not baseline.",
            })
            continue

        if resource is None:
            results.append({
                "result": "MISSING",
                "resource_type": resource_type,
                "resource_key": resource_key,
                "display_name": baseline_row["display_name"],
                "expected_status": baseline_row["expected_status"],
                "actual_status": None,
                "baseline_state": baseline_row["baseline_state"],
                "note": "Baseline resource is absent from observation.",
            })
            continue

        expected_status = baseline_row["expected_status"]
        actual_status = resource.get("status")

        if actual_status == expected_status:
            result = "MATCH"
            note = baseline_row["note"]
        else:
            result = "STATUS-CHANGED"
            note = (
                f"Expected {expected_status!r}; "
                f"observed {actual_status!r}."
            )

        results.append({
            "result": result,
            "resource_type": resource_type,
            "resource_key": resource_key,
            "display_name": (
                current_display_name(resource)
                or baseline_row["display_name"]
            ),
            "expected_status": expected_status,
            "actual_status": actual_status,
            "baseline_state": baseline_row["baseline_state"],
            "note": note,
        })

    return results


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compare one stored PVE observation against "
            "the authoritative RackMarshal resource baseline."
        )
    )

    parser.add_argument(
        "--observation-id",
        type=int,
        required=True,
        help="Stored observation ID to compare.",
    )

    args = parser.parse_args()

    connection = sqlite3.connect(
        f"file:{DB_FILE}?mode=ro",
        uri=True,
    )

    connection.row_factory = sqlite3.Row

    try:
        observation_row, payload, resources = load_observation(
            connection,
            args.observation_id,
        )

        baseline = load_baseline(connection)

        results = compare(
            resources,
            baseline,
        )

    except CompareError as exc:
        print(
            f"COMPARE ERROR: {exc}",
            file=sys.stderr,
        )
        return 2

    except sqlite3.Error as exc:
        print(
            f"DATABASE ERROR: {exc}",
            file=sys.stderr,
        )
        return 3

    finally:
        connection.close()

    counts = {
        "MATCH": 0,
        "STATUS-CHANGED": 0,
        "MISSING": 0,
        "NEW": 0,
    }

    for result in results:
        counts[result["result"]] += 1

    output = {
        "schema_version": 1,
        "comparator": "pve_resource_baseline",
        "observation_id": args.observation_id,
        "observed_at": observation_row["observed_at"],
        "baseline_resources": len(baseline),
        "observed_resources": len(resources),
        "result_count": len(results),
        "summary": counts,
        "differences": [
            result
            for result in results
            if result["result"] != "MATCH"
        ],
    }

    print(
        json.dumps(
            output,
            indent=2,
            sort_keys=False,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
