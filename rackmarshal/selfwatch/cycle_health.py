#!/usr/bin/env python3
"""Record durable RackMarshal systemd cycle health.

Intended callers:
- ExecStartPost: record SUCCESS after a completed cycle
- OnFailure handler: record FAILED after a failed cycle

The recorder only writes cycle_health. It does not create incidents,
enqueue notifications, or inspect systemd.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rackmarshal.core.config import state_db


VALID_STATES = {"SUCCESS", "FAILED"}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def record(
    db_path: Path,
    unit_name: str,
    health_state: str,
    exit_code: int | None,
    exit_status: int | None,
    detail: dict,
) -> dict:
    if health_state not in VALID_STATES:
        raise ValueError(f"invalid health state: {health_state}")

    now = utc_now()
    detail_json = json.dumps(
        detail,
        sort_keys=True,
        separators=(",", ":"),
    )

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute(
            """
            SELECT failure_count
            FROM cycle_health
            WHERE unit_name = ?
            """,
            (unit_name,),
        ).fetchone()

        previous_failure_count = (
            int(existing["failure_count"])
            if existing is not None
            else 0
        )

        failure_count = (
            previous_failure_count + 1
            if health_state == "FAILED"
            else previous_failure_count
        )

        last_success_at = now if health_state == "SUCCESS" else None
        last_failure_at = now if health_state == "FAILED" else None

        conn.execute(
            """
            INSERT INTO cycle_health (
                unit_name,
                health_state,
                last_result_at,
                last_success_at,
                last_failure_at,
                failure_count,
                last_exit_code,
                last_exit_status,
                detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unit_name) DO UPDATE SET
                health_state = excluded.health_state,
                last_result_at = excluded.last_result_at,
                last_success_at = CASE
                    WHEN excluded.health_state = 'SUCCESS'
                    THEN excluded.last_result_at
                    ELSE cycle_health.last_success_at
                END,
                last_failure_at = CASE
                    WHEN excluded.health_state = 'FAILED'
                    THEN excluded.last_result_at
                    ELSE cycle_health.last_failure_at
                END,
                failure_count = excluded.failure_count,
                last_exit_code = excluded.last_exit_code,
                last_exit_status = excluded.last_exit_status,
                detail_json = excluded.detail_json
            """,
            (
                unit_name,
                health_state,
                now,
                last_success_at,
                last_failure_at,
                failure_count,
                exit_code,
                exit_status,
                detail_json,
            ),
        )

        conn.commit()

        row = conn.execute(
            """
            SELECT *
            FROM cycle_health
            WHERE unit_name = ?
            """,
            (unit_name,),
        ).fetchone()

        return dict(row)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record RackMarshal cycle execution health"
    )
    parser.add_argument("--unit", required=True)
    parser.add_argument(
        "--state",
        required=True,
        choices=sorted(VALID_STATES),
    )
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--exit-status", type=int, default=None)
    parser.add_argument("--detail", default="{}")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    try:
        detail = json.loads(args.detail)
    except json.JSONDecodeError as exc:
        parser.error(f"--detail must be valid JSON: {exc}")

    if not isinstance(detail, dict):
        parser.error("--detail must decode to a JSON object")

    db_path = args.db or state_db()

    result = record(
        db_path=db_path,
        unit_name=args.unit,
        health_state=args.state,
        exit_code=args.exit_code,
        exit_status=args.exit_status,
        detail=detail,
    )

    print(
        json.dumps(
            {
                "schema_version": 1,
                "recorder": "cycle_health",
                "status": "OK",
                "row": result,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
