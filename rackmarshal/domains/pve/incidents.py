#!/usr/bin/env python3

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from rackmarshal.core.config import install_root, state_db, venv_python

# Phase 2 Step 13: derive PYTHON/COMPARATOR from config helpers
# (defaults = today's layout).
DB_FILE = state_db()
_ROOT = install_root()
PYTHON = str(venv_python())
COMPARATOR = [PYTHON, "-m", "rackmarshal.domains.pve.comparator"]

ALLOWED_EVENT_TYPES = {
    "STATUS-CHANGED",
    "MISSING",
    "NEW",
}


class IncidentProcessorError(Exception):
    pass


def run_comparator(observation_id):
    result = subprocess.run(
        COMPARATOR + [
            "--observation-id",
            str(observation_id),
        ],
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        detail = result.stderr.strip()

        raise IncidentProcessorError(
            "comparator failed"
            + (f": {detail}" if detail else "")
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise IncidentProcessorError(
            "comparator returned invalid JSON"
        ) from exc

    if data.get("schema_version") != 1:
        raise IncidentProcessorError(
            "unsupported comparator schema"
        )

    if data.get("comparator") != "pve_resource_baseline":
        raise IncidentProcessorError(
            "unexpected comparator identity"
        )

    if data.get("observation_id") != observation_id:
        raise IncidentProcessorError(
            "comparator observation ID mismatch"
        )

    if not isinstance(data.get("differences"), list):
        raise IncidentProcessorError(
            "comparator differences is not an array"
        )

    return data


def get_observation_time(connection, observation_id):
    row = connection.execute(
        """
        SELECT observed_at
        FROM observations
        WHERE id = ?
        """,
        (observation_id,),
    ).fetchone()

    if row is None:
        raise IncidentProcessorError(
            f"observation {observation_id} does not exist"
        )

    return row[0]


def normalize_difference(difference):
    event_type = difference.get("result")

    if event_type not in ALLOWED_EVENT_TYPES:
        raise IncidentProcessorError(
            f"unsupported difference type: {event_type!r}"
        )

    resource_type = difference.get("resource_type")
    resource_key = difference.get("resource_key")

    if not isinstance(resource_type, str) or not resource_type:
        raise IncidentProcessorError(
            "invalid resource_type"
        )

    if not isinstance(resource_key, str) or not resource_key:
        raise IncidentProcessorError(
            "invalid resource_key"
        )

    return {
        "incident_type": event_type,
        "resource_type": resource_type,
        "resource_key": resource_key,
        "display_name": difference.get("display_name"),
        "baseline_state": difference.get("baseline_state"),
        "expected_status": difference.get("expected_status"),
        "abnormal_status": difference.get("actual_status"),
        "note": difference.get("note"),
    }


def load_open_incidents(connection):
    rows = connection.execute(
        """
        SELECT *
        FROM resource_incidents
        WHERE incident_state = 'OPEN'
        """
    ).fetchall()

    return {
        (row["resource_type"], row["resource_key"]): row
        for row in rows
    }



def expected_next_pve_observation(
    connection,
    checkpoint,
):
    row = connection.execute(
        """
        SELECT MIN(id)
        FROM observations
        WHERE collector = 'pve_cluster_resources'
          AND id > ?
        """,
        (checkpoint,),
    ).fetchone()

    expected = row[0]

    if expected is None:
        raise IncidentProcessorError(
            "no unprocessed pve_cluster_resources "
            "observation exists"
        )

    return expected


def preflight_processing_order(observation_id):
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        ledger_row = connection.execute(
            """
            SELECT
                observation_id,
                processing_kind,
                differences_detected,
                incidents_opened,
                incidents_ongoing,
                incidents_recovered
            FROM incident_processing
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()

        if ledger_row is not None:
            return {
                "schema_version": 1,
                "processor": "pve_resource_incidents",
                "observation_id": observation_id,
                "differences_detected":
                    ledger_row["differences_detected"],
                "incidents_opened":
                    ledger_row["incidents_opened"],
                "incidents_ongoing":
                    ledger_row["incidents_ongoing"],
                "incidents_recovered":
                    ledger_row["incidents_recovered"],
                "incidents_already_processed": 0,
                "opened_incident_ids": [],
                "ongoing_incident_ids": [],
                "recovered_incident_ids": [],
                "already_processed_incident_ids": [],
                "processing_replay": True,
                "processing_kind":
                    ledger_row["processing_kind"],
            }

        checkpoint_row = connection.execute(
            """
            SELECT MAX(observation_id) AS observation_id
            FROM incident_processing
            """
        ).fetchone()

        checkpoint = checkpoint_row["observation_id"]

        if checkpoint is None:
            raise IncidentProcessorError(
                "incident processing ledger has no checkpoint"
            )

        expected_observation_id = (
            expected_next_pve_observation(
                connection,
                checkpoint,
            )
        )

        if observation_id < expected_observation_id:
            raise IncidentProcessorError(
                "stale observation: "
                f"{observation_id}; "
                f"processing checkpoint is {checkpoint}"
            )

        if observation_id > expected_observation_id:
            raise IncidentProcessorError(
                "observation gap: "
                f"expected {expected_observation_id}, "
                f"received {observation_id}"
            )

        return None

    finally:
        connection.close()


def process(observation_id):
    replay = preflight_processing_order(
        observation_id
    )

    if replay is not None:
        return replay

    comparison = run_comparator(observation_id)

    differences = [
        normalize_difference(item)
        for item in comparison["differences"]
    ]

    current_abnormal = {
        (
            item["resource_type"],
            item["resource_key"],
        ): item
        for item in differences
    }

    if len(current_abnormal) != len(differences):
        raise IncidentProcessorError(
            "duplicate resource differences detected"
        )

    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        observed_at = get_observation_time(
            connection,
            observation_id,
        )

        connection.execute("BEGIN IMMEDIATE")

        ledger_row = connection.execute(
            """
            SELECT
                observation_id,
                processing_kind,
                differences_detected,
                incidents_opened,
                incidents_ongoing,
                incidents_recovered
            FROM incident_processing
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()

        if ledger_row is not None:
            connection.commit()

            return {
                "schema_version": 1,
                "processor": "pve_resource_incidents",
                "observation_id": observation_id,
                "differences_detected":
                    ledger_row["differences_detected"],
                "incidents_opened":
                    ledger_row["incidents_opened"],
                "incidents_ongoing":
                    ledger_row["incidents_ongoing"],
                "incidents_recovered":
                    ledger_row["incidents_recovered"],
                "incidents_already_processed": 0,
                "opened_incident_ids": [],
                "ongoing_incident_ids": [],
                "recovered_incident_ids": [],
                "already_processed_incident_ids": [],
                "processing_replay": True,
                "processing_kind":
                    ledger_row["processing_kind"],
            }

        checkpoint_row = connection.execute(
            """
            SELECT MAX(observation_id) AS observation_id
            FROM incident_processing
            """
        ).fetchone()

        checkpoint = checkpoint_row["observation_id"]

        if checkpoint is None:
            raise IncidentProcessorError(
                "incident processing ledger has no checkpoint"
            )

        expected_observation_id = (
            expected_next_pve_observation(
                connection,
                checkpoint,
            )
        )

        if observation_id < expected_observation_id:
            raise IncidentProcessorError(
                "stale observation: "
                f"{observation_id}; "
                f"processing checkpoint is {checkpoint}"
            )

        if observation_id > expected_observation_id:
            raise IncidentProcessorError(
                "observation gap: "
                f"expected {expected_observation_id}, "
                f"received {observation_id}"
            )

        open_incidents = load_open_incidents(connection)

        opened = []
        ongoing = []
        recovered = []
        already_processed = []

        for key, difference in current_abnormal.items():
            existing = open_incidents.get(key)

            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO resource_incidents (
                        resource_type,
                        resource_key,
                        display_name,
                        incident_type,
                        incident_state,
                        baseline_state,
                        expected_status,
                        abnormal_status,
                        opened_observation_id,
                        last_abnormal_observation_id,
                        opened_at,
                        last_abnormal_at,
                        occurrence_count,
                        note,
                        updated_at
                    )
                    VALUES (
                        ?, ?, ?, ?, 'OPEN',
                        ?, ?, ?,
                        ?, ?,
                        ?, ?,
                        1,
                        ?,
                        strftime(
                            '%Y-%m-%dT%H:%M:%fZ',
                            'now'
                        )
                    )
                    """,
                    (
                        difference["resource_type"],
                        difference["resource_key"],
                        difference["display_name"],
                        difference["incident_type"],
                        difference["baseline_state"],
                        difference["expected_status"],
                        difference["abnormal_status"],
                        observation_id,
                        observation_id,
                        observed_at,
                        observed_at,
                        difference["note"],
                    ),
                )

                opened.append(cursor.lastrowid)

            else:
                same_condition = (
                    existing["incident_type"]
                    == difference["incident_type"]
                    and existing["expected_status"]
                    == difference["expected_status"]
                    and existing["abnormal_status"]
                    == difference["abnormal_status"]
                )

                if same_condition:
                    if (
                        existing["last_abnormal_observation_id"]
                        == observation_id
                    ):
                        already_processed.append(
                            existing["id"]
                        )

                    else:
                        connection.execute(
                            """
                            UPDATE resource_incidents
                            SET
                                display_name = ?,
                                baseline_state = ?,
                                last_abnormal_observation_id = ?,
                                last_abnormal_at = ?,
                                occurrence_count = occurrence_count + 1,
                                note = ?,
                                updated_at = strftime(
                                    '%Y-%m-%dT%H:%M:%fZ',
                                    'now'
                                )
                            WHERE id = ?
                            """,
                            (
                                difference["display_name"],
                                difference["baseline_state"],
                                observation_id,
                                observed_at,
                                difference["note"],
                                existing["id"],
                            ),
                        )

                        ongoing.append(existing["id"])

                else:
                    connection.execute(
                        """
                        UPDATE resource_incidents
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
                            existing["id"],
                        ),
                    )

                    recovered.append(existing["id"])

                    cursor = connection.execute(
                        """
                        INSERT INTO resource_incidents (
                            resource_type,
                            resource_key,
                            display_name,
                            incident_type,
                            incident_state,
                            baseline_state,
                            expected_status,
                            abnormal_status,
                            opened_observation_id,
                            last_abnormal_observation_id,
                            opened_at,
                            last_abnormal_at,
                            occurrence_count,
                            note,
                            updated_at
                        )
                        VALUES (
                            ?, ?, ?, ?, 'OPEN',
                            ?, ?, ?,
                            ?, ?,
                            ?, ?,
                            1,
                            ?,
                            strftime(
                                '%Y-%m-%dT%H:%M:%fZ',
                                'now'
                            )
                        )
                        """,
                        (
                            difference["resource_type"],
                            difference["resource_key"],
                            difference["display_name"],
                            difference["incident_type"],
                            difference["baseline_state"],
                            difference["expected_status"],
                            difference["abnormal_status"],
                            observation_id,
                            observation_id,
                            observed_at,
                            observed_at,
                            difference["note"],
                        ),
                    )

                    opened.append(cursor.lastrowid)

        current_keys = set(current_abnormal)

        for key, existing in open_incidents.items():
            if key in current_keys:
                continue

            connection.execute(
                """
                UPDATE resource_incidents
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
                    existing["id"],
                ),
            )

            recovered.append(existing["id"])

        connection.execute(
            """
            INSERT INTO incident_processing (
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
                ?
            )
            """,
            (
                observation_id,
                len(differences),
                len(opened),
                len(ongoing),
                len(recovered),
                (
                    "Incident state and processing checkpoint "
                    "committed atomically."
                ),
            ),
        )

        connection.commit()

        return {
            "schema_version": 1,
            "processor": "pve_resource_incidents",
            "observation_id": observation_id,
            "differences_detected": len(differences),
            "incidents_opened": len(opened),
            "incidents_ongoing": len(ongoing),
            "incidents_recovered": len(recovered),
            "incidents_already_processed": len(already_processed),
            "opened_incident_ids": opened,
            "ongoing_incident_ids": ongoing,
            "recovered_incident_ids": recovered,
            "already_processed_incident_ids": already_processed,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Process RackMarshal PVE observations into "
            "resource incident state transitions."
        )
    )

    parser.add_argument(
        "--observation-id",
        type=int,
        required=True,
    )

    args = parser.parse_args()

    if args.observation_id <= 0:
        print(
            "INCIDENT PROCESSOR ERROR: "
            "observation ID must be positive",
            file=sys.stderr,
        )
        return 2

    try:
        output = process(args.observation_id)

    except (
        IncidentProcessorError,
        sqlite3.Error,
        OSError,
    ) as exc:
        print(
            f"INCIDENT PROCESSOR ERROR: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            output,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
