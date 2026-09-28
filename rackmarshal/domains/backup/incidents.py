#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from rackmarshal.core.config import state_db


DEFAULT_DB = state_db()

VALID_OUTCOMES = {
    "MATCH",
    "STATUS-CHANGED",
    "MISSING",
    "NEW",
}

ABNORMAL_OUTCOMES = {
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


def fail(message):
    print(
        json.dumps(
            {
                "schema_version": 1,
                "processor": "backup_incidents",
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

    normalized = []

    seen = set()

    for result in results:
        if not isinstance(result, dict):
            fail("each result must be an object")

        resource_type = result.get("resource_type")
        resource_key = result.get("resource_key")
        display_name = result.get("display_name")
        outcome = result.get("outcome")
        baseline_state = result.get("baseline_state")
        changes = result.get("changes", [])

        if resource_type not in VALID_RESOURCE_TYPES:
            fail(
                f"invalid resource_type: {resource_type!r}"
            )

        if (
            not isinstance(resource_key, str)
            or not resource_key
        ):
            fail("invalid resource_key")

        if (
            not isinstance(display_name, str)
            or not display_name
        ):
            fail("invalid display_name")

        if outcome not in VALID_OUTCOMES:
            fail(f"invalid outcome: {outcome!r}")

        if not isinstance(changes, list):
            fail("changes must be a list")

        identity = (resource_type, resource_key)

        if identity in seen:
            fail(
                f"duplicate comparator resource: "
                f"{identity!r}"
            )

        seen.add(identity)

        normalized.append(
            {
                "resource_type": resource_type,
                "resource_key": resource_key,
                "display_name": display_name,
                "outcome": outcome,
                "baseline_state": baseline_state,
                "changes": changes,
            }
        )

    return (
        observation_id,
        observed_at,
        normalized,
    )


def changes_json(changes):
    return json.dumps(
        changes,
        separators=(",", ":"),
        sort_keys=True,
    )


def replay_result(row):
    return {
        "schema_version": 1,
        "processor": "backup_incidents",
        "status": "REPLAY",
        "observation_id": row["observation_id"],
        "differences_detected":
            row["differences_detected"],
        "incidents_opened":
            row["incidents_opened"],
        "incidents_ongoing":
            row["incidents_ongoing"],
        "incidents_recovered":
            row["incidents_recovered"],
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB,
    )

    args = parser.parse_args()

    (
        observation_id,
        observed_at,
        results,
    ) = load_input()

    try:
        conn = sqlite3.connect(str(args.database))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")

        observation = conn.execute(
            """
            SELECT
                id,
                collector,
                observed_at
            FROM observations
            WHERE id = ?
            """,
            (observation_id,),
        ).fetchone()

        if observation is None:
            fail(
                f"observation {observation_id} "
                "does not exist"
            )

        if observation["collector"] != "backup_domain":
            fail(
                f"observation {observation_id} "
                "is not backup_domain"
            )

        if observation["observed_at"] != observed_at:
            fail(
                "comparator observed_at does not "
                "match stored observation"
            )

        prior_processing = conn.execute(
            """
            SELECT *
            FROM backup_incident_processing
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()

        if prior_processing is not None:
            conn.rollback()

            print(
                json.dumps(
                    replay_result(prior_processing),
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return

        checkpoint = conn.execute(
            """
            SELECT MAX(observation_id)
            FROM backup_incident_processing
            """
        ).fetchone()[0]

        if checkpoint is None:
            fail(
                "backup incident processor has "
                "no bootstrap checkpoint"
            )

        expected_next = conn.execute(
            """
            SELECT MIN(id)
            FROM observations
            WHERE collector = 'backup_domain'
              AND id > ?
            """,
            (checkpoint,),
        ).fetchone()[0]

        if expected_next is None:
            fail(
                "no unprocessed backup_domain "
                "observation exists"
            )

        if observation_id != expected_next:
            if observation_id < expected_next:
                fail(
                    f"stale backup observation "
                    f"{observation_id}; expected "
                    f"{expected_next}"
                )

            fail(
                f"backup observation gap: "
                f"expected {expected_next}, "
                f"received {observation_id}"
            )

        differences_detected = 0
        incidents_opened = 0
        incidents_ongoing = 0
        incidents_recovered = 0

        for result in results:
            resource_type = result["resource_type"]
            resource_key = result["resource_key"]
            display_name = result["display_name"]
            outcome = result["outcome"]
            baseline_state = result["baseline_state"]
            change_json = changes_json(
                result["changes"]
            )

            if outcome == "MATCH":
                open_rows = conn.execute(
                    """
                    SELECT id
                    FROM backup_incidents
                    WHERE resource_type = ?
                      AND resource_key = ?
                      AND incident_state = 'OPEN'
                    ORDER BY id
                    """,
                    (
                        resource_type,
                        resource_key,
                    ),
                ).fetchall()

                for open_row in open_rows:
                    conn.execute(
                        """
                        UPDATE backup_incidents
                        SET
                            incident_state =
                                'RECOVERED',
                            recovered_observation_id = ?,
                            recovered_at = ?,
                            updated_at = strftime(
                                '%Y-%m-%dT%H:%M:%fZ',
                                'now'
                            )
                        WHERE id = ?
                        """,
                        (
                            observation_id,
                            observed_at,
                            open_row["id"],
                        ),
                    )

                    incidents_recovered += 1

                continue

            differences_detected += 1

            #
            # Every abnormal comparator result must
            # already have a durable event row.
            #
            event = conn.execute(
                """
                SELECT id
                FROM backup_events
                WHERE observation_id = ?
                  AND resource_type = ?
                  AND resource_key = ?
                  AND outcome = ?
                """,
                (
                    observation_id,
                    resource_type,
                    resource_key,
                    outcome,
                ),
            ).fetchone()

            if event is None:
                fail(
                    "missing backup event for "
                    f"{resource_type}/"
                    f"{resource_key}/"
                    f"{outcome}"
                )

            event_id = event["id"]

            #
            # If classification changed, recover any
            # other open incident for this resource.
            #
            other_open = conn.execute(
                """
                SELECT id
                FROM backup_incidents
                WHERE resource_type = ?
                  AND resource_key = ?
                  AND incident_state = 'OPEN'
                  AND incident_type <> ?
                ORDER BY id
                """,
                (
                    resource_type,
                    resource_key,
                    outcome,
                ),
            ).fetchall()

            for open_row in other_open:
                conn.execute(
                    """
                    UPDATE backup_incidents
                    SET
                        incident_state = 'RECOVERED',
                        recovered_observation_id = ?,
                        recovered_at = ?,
                        updated_at = strftime(
                            '%Y-%m-%dT%H:%M:%fZ',
                            'now'
                        )
                    WHERE id = ?
                    """,
                    (
                        observation_id,
                        observed_at,
                        open_row["id"],
                    ),
                )

                incidents_recovered += 1

            existing = conn.execute(
                """
                SELECT id
                FROM backup_incidents
                WHERE resource_type = ?
                  AND resource_key = ?
                  AND incident_type = ?
                  AND incident_state = 'OPEN'
                """,
                (
                    resource_type,
                    resource_key,
                    outcome,
                ),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO backup_incidents (
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
                        ?,
                        ?,
                        ?,
                        ?,
                        'OPEN',
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        1,
                        ?,
                        ?
                    )
                    """,
                    (
                        resource_type,
                        resource_key,
                        display_name,
                        outcome,
                        baseline_state,
                        event_id,
                        event_id,
                        observation_id,
                        observation_id,
                        observed_at,
                        observed_at,
                        change_json,
                        change_json,
                    ),
                )

                incidents_opened += 1

            else:
                conn.execute(
                    """
                    UPDATE backup_incidents
                    SET
                        display_name = ?,
                        baseline_state = ?,
                        last_event_id = ?,
                        last_abnormal_observation_id = ?,
                        last_abnormal_at = ?,
                        occurrence_count =
                            occurrence_count + 1,
                        latest_changes_json = ?,
                        updated_at = strftime(
                            '%Y-%m-%dT%H:%M:%fZ',
                            'now'
                        )
                    WHERE id = ?
                    """,
                    (
                        display_name,
                        baseline_state,
                        event_id,
                        observation_id,
                        observed_at,
                        change_json,
                        existing["id"],
                    ),
                )

                incidents_ongoing += 1

        conn.execute(
            """
            INSERT INTO backup_incident_processing (
                observation_id,
                processing_kind,
                differences_detected,
                incidents_opened,
                incidents_ongoing,
                incidents_recovered,
                note
            )
            VALUES (
                ?,
                'PROCESSED',
                ?,
                ?,
                ?,
                ?,
                'Backup Domain incident processing completed.'
            )
            """,
            (
                observation_id,
                differences_detected,
                incidents_opened,
                incidents_ongoing,
                incidents_recovered,
            ),
        )

        conn.commit()

    except sqlite3.Error as exc:
        try:
            conn.rollback()
        except Exception:
            pass

        fail(f"database processing failed: {exc}")

    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(
        json.dumps(
            {
                "schema_version": 1,
                "processor": "backup_incidents",
                "status": "OK",
                "observation_id": observation_id,
                "differences_detected":
                    differences_detected,
                "incidents_opened":
                    incidents_opened,
                "incidents_ongoing":
                    incidents_ongoing,
                "incidents_recovered":
                    incidents_recovered,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
