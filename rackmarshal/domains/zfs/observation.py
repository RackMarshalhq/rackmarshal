#!/usr/bin/env python3

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
                "writer": "zfs_observation",
                "error": message,
            },
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )
    raise SystemExit(rc)


def validate(payload):
    if not isinstance(payload, dict):
        fail("input must be a JSON object")

    if payload.get("schema_version") != 1:
        fail("unsupported schema_version")

    if payload.get("collector") != "zfs_status":
        fail("unexpected collector")

    observed_at = payload.get("observed_at")

    if not isinstance(observed_at, str) or not observed_at:
        fail("missing or invalid observed_at")

    source = payload.get("source")

    if not isinstance(source, str) or not source:
        fail("missing or invalid source")

    if payload.get("host_key_verified") is not True:
        fail("host_key_verified must be true")

    pool_count = payload.get("pool_count")

    if (
        not isinstance(pool_count, int)
        or isinstance(pool_count, bool)
        or pool_count < 0
    ):
        fail("pool_count must be a non-negative integer")

    pools = payload.get("pools")

    if not isinstance(pools, list):
        fail("pools must be an array")

    if pool_count != len(pools):
        fail("pool_count does not match pools array length")

    names = set()

    for pool in pools:
        if not isinstance(pool, dict):
            fail("each pool must be an object")

        name = pool.get("name")

        if not isinstance(name, str) or not name:
            fail("pool has missing or invalid name")

        if name in names:
            fail(f"duplicate pool name: {name}")

        names.add(name)

        state = pool.get("state")

        if not isinstance(state, str) or not state:
            fail(f"pool {name} has missing or invalid state")

        error_count = pool.get("error_count")

        if (
            not isinstance(error_count, int)
            or isinstance(error_count, bool)
            or error_count < 0
        ):
            fail(
                f"pool {name} has invalid error_count"
            )

    return {
        "observed_at": observed_at,
        "source": source,
        "schema_version": payload["schema_version"],
        "host_key_verified": 1,
        "pool_count": pool_count,
        "payload_json": json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ),
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid input JSON: {exc}")

    row = validate(payload)

    try:
        connection = sqlite3.connect(
            DB_PATH,
            timeout=10,
        )
    except sqlite3.Error as exc:
        fail(f"unable to open database: {exc}")

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            INSERT INTO zfs_observations (
                observed_at,
                source,
                schema_version,
                host_key_verified,
                pool_count,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["observed_at"],
                row["source"],
                row["schema_version"],
                row["host_key_verified"],
                row["pool_count"],
                row["payload_json"],
            ),
        )

        observation_id = cursor.lastrowid

        connection.commit()

    except sqlite3.Error as exc:
        connection.rollback()
        fail(f"database write failed: {exc}")

    finally:
        connection.close()

    print(
        json.dumps(
            {
                "schema_version": 1,
                "writer": "zfs_observation",
                "observation_id": observation_id,
                "observed_at": row["observed_at"],
                "pool_count": row["pool_count"],
                "status": "recorded",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
