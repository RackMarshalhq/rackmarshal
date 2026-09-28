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


def compare(comparator, db, observation_id):
    r = subprocess.run(
        (list(comparator) if isinstance(comparator, (list, tuple)) else [comparator]) + [
            "--db", db,
            "--observation-id", str(observation_id),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(r.stdout)


def get_next_observation(conn):
    row = conn.execute("""
        SELECT COALESCE(MAX(observation_id), 0)
        FROM ha_incident_processing
    """).fetchone()

    checkpoint = row[0]

    return conn.execute("""
        SELECT id
        FROM observations
        WHERE collector='home_assistant'
          AND id > ?
        ORDER BY id
        LIMIT 1
    """, (checkpoint,)).fetchone()


def get_event(conn, observation_id, result):
    return conn.execute("""
        SELECT
            id,
            changes_json
        FROM ha_events
        WHERE observation_id=?
          AND resource_type=?
          AND resource_key=?
          AND outcome=?
    """, (
        observation_id,
        result["resource_type"],
        result["resource_key"],
        result["outcome"],
    )).fetchone()


def get_open_incident(conn, resource_type, resource_key):
    return conn.execute("""
        SELECT
            id,
            incident_type,
            occurrence_count
        FROM ha_incidents
        WHERE resource_type=?
          AND resource_key=?
          AND incident_state='OPEN'
        ORDER BY id DESC
        LIMIT 1
    """, (
        resource_type,
        resource_key,
    )).fetchone()


def bootstrap(conn, observation_id, differences):
    conn.execute("""
        INSERT INTO ha_incident_processing (
            observation_id,
            processing_kind,
            differences_detected,
            incidents_opened,
            incidents_ongoing,
            incidents_recovered,
            note
        )
        VALUES (?, 'BOOTSTRAP', ?, 0, 0, 0, ?)
    """, (
        observation_id,
        differences,
        "Initial Home Assistant incident-processing checkpoint",
    ))


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
        "--bootstrap-observation",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        if args.bootstrap_observation is not None:
            existing = conn.execute("""
                SELECT processing_kind
                FROM ha_incident_processing
                WHERE observation_id=?
            """, (
                args.bootstrap_observation,
            )).fetchone()

            if existing:
                print(json.dumps({
                    "observation_id": args.bootstrap_observation,
                    "processing_kind": existing[0],
                    "already_processed": True,
                }, indent=2, sort_keys=True))
                return 0

            x = compare(
                args.comparator,
                args.db,
                args.bootstrap_observation,
            )

            if x["differences"] != 0:
                raise RuntimeError(
                    "Bootstrap observation is not healthy; "
                    f"differences={x['differences']}"
                )

            with conn:
                bootstrap(
                    conn,
                    args.bootstrap_observation,
                    x["differences"],
                )

            print(json.dumps({
                "observation_id": args.bootstrap_observation,
                "processing_kind": "BOOTSTRAP",
                "differences_detected": 0,
                "incidents_opened": 0,
                "incidents_ongoing": 0,
                "incidents_recovered": 0,
            }, indent=2, sort_keys=True))

            return 0

        next_row = get_next_observation(conn)

        if next_row is None:
            print(json.dumps({
                "status": "NO-NEW-OBSERVATION",
            }, indent=2, sort_keys=True))
            return 0

        observation_id = next_row[0]

        x = compare(
            args.comparator,
            args.db,
            observation_id,
        )

        opened = 0
        ongoing = 0
        recovered = 0

        abnormal_keys = set()

        with conn:
            for result in x["results"]:
                outcome = result["outcome"]

                key = (
                    result["resource_type"],
                    result["resource_key"],
                )

                if outcome == "MATCH":
                    incident = get_open_incident(
                        conn,
                        result["resource_type"],
                        result["resource_key"],
                    )

                    if incident is not None:
                        conn.execute("""
                            UPDATE ha_incidents
                            SET
                                incident_state='RECOVERED',
                                recovered_observation_id=?,
                                recovered_at=?,
                                updated_at=strftime(
                                    '%Y-%m-%dT%H:%M:%fZ',
                                    'now'
                                )
                            WHERE id=?
                        """, (
                            observation_id,
                            x["observed_at"],
                            incident[0],
                        ))

                        recovered += 1

                    continue

                abnormal_keys.add(key)

                event = get_event(
                    conn,
                    observation_id,
                    result,
                )

                if event is None:
                    raise RuntimeError(
                        "Required HA event missing for "
                        f"observation={observation_id} "
                        f"resource={result['resource_key']} "
                        f"outcome={outcome}"
                    )

                event_id, changes_json = event

                incident = get_open_incident(
                    conn,
                    result["resource_type"],
                    result["resource_key"],
                )

                if incident is None:
                    conn.execute("""
                        INSERT INTO ha_incidents (
                            resource_type,
                            resource_key,
                            display_name,
                            incident_type,
                            incident_state,
                            baseline_state,
                            opened_event_id,
                            last_event_id,
                            opened_observation_id,
                            last_abnormal_observation_id,
                            opened_at,
                            last_abnormal_at,
                            occurrence_count,
                            opening_changes_json,
                            latest_changes_json
                        )
                        VALUES (
                            ?, ?, ?, ?, 'OPEN', ?,
                            ?, ?, ?, ?, ?, ?, 1, ?, ?
                        )
                    """, (
                        result["resource_type"],
                        result["resource_key"],
                        result["display_name"],
                        outcome,
                        result.get("baseline_state"),
                        event_id,
                        event_id,
                        observation_id,
                        observation_id,
                        x["observed_at"],
                        x["observed_at"],
                        changes_json,
                        changes_json,
                    ))

                    opened += 1

                else:
                    conn.execute("""
                        UPDATE ha_incidents
                        SET
                            last_event_id=?,
                            last_abnormal_observation_id=?,
                            last_abnormal_at=?,
                            occurrence_count=occurrence_count+1,
                            latest_changes_json=?,
                            updated_at=strftime(
                                '%Y-%m-%dT%H:%M:%fZ',
                                'now'
                            )
                        WHERE id=?
                    """, (
                        event_id,
                        observation_id,
                        x["observed_at"],
                        changes_json,
                        incident[0],
                    ))

                    ongoing += 1

            conn.execute("""
                INSERT INTO ha_incident_processing (
                    observation_id,
                    processing_kind,
                    differences_detected,
                    incidents_opened,
                    incidents_ongoing,
                    incidents_recovered,
                    note
                )
                VALUES (
                    ?, 'PROCESSED', ?, ?, ?, ?, ?
                )
            """, (
                observation_id,
                x["differences"],
                opened,
                ongoing,
                recovered,
                "Home Assistant incident lifecycle processing",
            ))

        print(json.dumps({
            "observation_id": observation_id,
            "differences_detected": x["differences"],
            "incidents_opened": opened,
            "incidents_ongoing": ongoing,
            "incidents_recovered": recovered,
        }, indent=2, sort_keys=True))

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
