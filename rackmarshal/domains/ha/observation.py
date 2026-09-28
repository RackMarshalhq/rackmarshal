#!/usr/bin/env python3

import datetime
import json
import sqlite3
import sys

from rackmarshal.core.config import state_db


DB = str(state_db())
EXPECTED_COLLECTOR = "home_assistant"


class WriterError(Exception):
    pass


def utc_now():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise WriterError(
            "stdin is not valid JSON"
        ) from exc

    if payload.get("collector") != EXPECTED_COLLECTOR:
        raise WriterError(
            "unexpected collector"
        )

    observed_at = payload.get("observed_at")
    source = payload.get("source")
    schema_version = payload.get("schema_version")
    tls_verified = payload.get("tls_verified")
    resource_count = payload.get("resource_count")

    if not observed_at:
        raise WriterError("observed_at missing")

    if not source:
        raise WriterError("source missing")

    if not isinstance(schema_version, int):
        raise WriterError(
            "schema_version invalid"
        )

    if tls_verified not in (0, 1):
        raise WriterError(
            "tls_verified invalid"
        )

    if (
        not isinstance(resource_count, int)
        or resource_count < 0
    ):
        raise WriterError(
            "resource_count invalid"
        )

    resources = payload.get("resources")

    if (
        not isinstance(resources, list)
        or len(resources) != resource_count
    ):
        raise WriterError(
            "resource_count does not match resources"
        )

    connection = sqlite3.connect(DB)

    try:
        cursor = connection.execute(
            """
            INSERT INTO observations (
                collector,
                observed_at,
                source,
                schema_version,
                tls_verified,
                resource_count,
                payload_json,
                recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                EXPECTED_COLLECTOR,
                observed_at,
                source,
                schema_version,
                tls_verified,
                resource_count,
                json.dumps(
                    payload,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                utc_now(),
            ),
        )

        observation_id = cursor.lastrowid

        connection.commit()

    finally:
        connection.close()

    print(
        json.dumps(
            {
                "status": "OK",
                "collector": EXPECTED_COLLECTOR,
                "observation_id": observation_id,
                "resource_count": resource_count,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except WriterError as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
