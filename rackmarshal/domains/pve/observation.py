#!/usr/bin/env python3

import json
import sqlite3
import sys
from pathlib import Path

from rackmarshal.core.config import state_db


DB_FILE = state_db()

EXPECTED_COLLECTOR = "pve_cluster_resources"
EXPECTED_SOURCE = "Proxmox VE API"
EXPECTED_SCHEMA_VERSION = 1


class ValidationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def validate_observation(data):
    require(isinstance(data, dict), "top-level JSON must be an object")

    required_fields = {
        "schema_version",
        "collector",
        "observed_at",
        "source",
        "tls_verified",
        "resource_count",
        "resources",
    }

    missing = required_fields - data.keys()
    require(not missing, f"missing required fields: {sorted(missing)}")

    require(
        data["schema_version"] == EXPECTED_SCHEMA_VERSION,
        f"unsupported schema_version: {data['schema_version']!r}",
    )

    require(
        data["collector"] == EXPECTED_COLLECTOR,
        f"unexpected collector: {data['collector']!r}",
    )

    require(
        data["source"] == EXPECTED_SOURCE,
        f"unexpected source: {data['source']!r}",
    )

    require(
        data["tls_verified"] is True,
        "refusing observation because tls_verified is not true",
    )

    require(
        isinstance(data["observed_at"], str) and data["observed_at"],
        "observed_at must be a non-empty string",
    )

    require(
        isinstance(data["resource_count"], int)
        and not isinstance(data["resource_count"], bool)
        and data["resource_count"] >= 0,
        "resource_count must be a non-negative integer",
    )

    require(
        isinstance(data["resources"], list),
        "resources must be an array",
    )

    require(
        data["resource_count"] == len(data["resources"]),
        (
            "resource_count does not match resources length: "
            f"{data['resource_count']} != {len(data['resources'])}"
        ),
    )

    for index, resource in enumerate(data["resources"]):
        require(
            isinstance(resource, dict),
            f"resource {index} must be an object",
        )

        require(
            isinstance(resource.get("type"), str)
            and resource["type"],
            f"resource {index} has no valid type",
        )

    return data


def read_input():
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"invalid JSON input: {exc}"
        ) from exc


def write_observation(data):
    payload_json = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    connection = sqlite3.connect(DB_FILE)

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            INSERT INTO observations (
                collector,
                observed_at,
                source,
                schema_version,
                tls_verified,
                resource_count,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["collector"],
                data["observed_at"],
                data["source"],
                data["schema_version"],
                1 if data["tls_verified"] else 0,
                data["resource_count"],
                payload_json,
            ),
        )

        observation_id = cursor.lastrowid
        connection.commit()

        return observation_id

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main():
    try:
        data = validate_observation(read_input())
        observation_id = write_observation(data)

    except ValidationError as exc:
        print(
            f"VALIDATION ERROR: {exc}",
            file=sys.stderr,
        )
        return 2

    except (OSError, sqlite3.Error) as exc:
        print(
            f"WRITE ERROR: {exc}",
            file=sys.stderr,
        )
        return 3

    print(
        json.dumps(
            {
                "status": "written",
                "observation_id": observation_id,
                "collector": data["collector"],
                "observed_at": data["observed_at"],
                "resource_count": data["resource_count"],
            },
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
