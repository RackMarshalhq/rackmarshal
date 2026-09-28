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
    "COUNTER-CHANGED",
    "MISSING",
    "NEW",
}

INCIDENT_OUTCOMES = {
    "STATUS-CHANGED",
    "MISSING",
    "NEW",
}

VALID_RESOURCE_TYPES = {
    "zfs_pool",
    "zfs_vdev",
}

VALID_BASELINE_STATES = {
    "VERIFIED",
    "EXPECTED",
    "KNOWN-ISSUE",
    "FAILED",
    "DECOMMISSIONED",
}


class ProcessorError(Exception):
    pass


def fail(message):
    print(
        json.dumps(
            {
                "schema_version": 1,
                "processor": "zfs_incidents",
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

    if payload.get("comparator") != "zfs_baseline":
        fail("unexpected comparator identity")

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

    return observation_id, observed_at, results


def normalize_result(result):
    if not isinstance(result, dict):
        raise ProcessorError(
            "each comparator result must be an object"
        )

    resource_type = result.get("resource_type")

    if resource_type not in VALID_RESOURCE_TYPES:
        raise ProcessorError(
            f"invalid resource_type: {resource_type!r}"
        )

    resource_key = result.get("resource_key")

    if not isinstance(resource_key, str) or not resource_key:
        raise ProcessorError("invalid resource_key")

    outcome = result.get("outcome")

    if outcome not in VALID_OUTCOMES:
        raise ProcessorError(
            f"invalid outcome: {outcome!r}"
        )

    baseline_state = result.get("baseline_state")

    if (
        baseline_state is not None
        and baseline_state not in VALID_BASELINE_STATES
    ):
        raise ProcessorError(
            f"invalid baseline_state: {baseline_state!r}"
        )

    if resource_type == "zfs_pool":
        pool_name = resource_key
        vdev_name = None

    else:
        pool_name = result.get("pool_name")
        vdev_name = result.get("vdev_name")

        if not isinstance(pool_name, str) or not pool_name:
            raise ProcessorError(
                "zfs_vdev result missing pool_name"
            )

        if not isinstance(vdev_name, str) or not vdev_name:
            raise ProcessorError(
                "zfs_vdev result missing vdev_name"
            )

    return {
        "resource_type": resource_type,
        "resource_key": resource_key,
        "pool_name": pool_name,
        "vdev_name": vdev_name,
        "outcome": outcome,
        "baseline_state": baseline_state,
    }


def close_incident(
    connection,
    incident_id,
    observation_id,
    observed_at,
):
    connection.execute(
        """
        UPDATE zfs_incidents
        SET
            incident_state='RECOVERED',
            recovered_observation_id=?,
            recovered_at=?,
            updated_at=strftime(
                '%Y-%m-%dT%H:%M:%fZ',
                'now'
            )
        WHERE id=?
          AND incident_state='OPEN'
        """,
        (
            observation_id,
            observed_at,
            incident_id,
        ),
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB,
    )

    args = parser.parse_args()

    try:
        (
            observation_id,
            observed_at,
            raw_results,
        ) = load_input()

        results = []
        seen_resources = set()

        for raw in raw_results:
            result = normalize_result(raw)

            resource_identity = (
                result["resource_type"],
                result["resource_key"],
            )

            if resource_identity in seen_resources:
                raise ProcessorError(
                    "duplicate comparator result for "
                    f"{resource_identity[0]} "
                    f"{resource_identity[1]}"
                )

            seen_resources.add(resource_identity)
            results.append(result)

        connection = sqlite3.connect(str(args.database))
        connection.row_factory = sqlite3.Row

        try:
            connection.execute("PRAGMA foreign_keys = ON")

            observation = connection.execute(
                """
                SELECT id, observed_at
                FROM zfs_observations
                WHERE id=?
                """,
                (observation_id,),
            ).fetchone()

            if observation is None:
                raise ProcessorError(
                    f"ZFS observation {observation_id} "
                    "does not exist"
                )

            if observation["observed_at"] != observed_at:
                raise ProcessorError(
                    "comparator observed_at does not "
                    "match stored observation"
                )

            connection.execute("BEGIN IMMEDIATE")

            checkpoint = connection.execute(
                """
                SELECT
                    differences_detected,
                    incidents_opened,
                    incidents_ongoing,
                    incidents_recovered
                FROM zfs_incident_processing
                WHERE observation_id=?
                """,
                (observation_id,),
            ).fetchone()

            if checkpoint is not None:
                connection.commit()

                print(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "processor":
                                "zfs_incidents",
                            "observation_id":
                                observation_id,
                            "differences_detected":
                                checkpoint[
                                    "differences_detected"
                                ],
                            "incidents_opened":
                                checkpoint[
                                    "incidents_opened"
                                ],
                            "incidents_ongoing":
                                checkpoint[
                                    "incidents_ongoing"
                                ],
                            "incidents_recovered":
                                checkpoint[
                                    "incidents_recovered"
                                ],
                            "processing_replay": True,
                            "status": "OK",
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                )
                return

            event_rows = connection.execute(
                """
                SELECT
                    id,
                    resource_type,
                    resource_key,
                    outcome,
                    baseline_state,
                    changes_json
                FROM zfs_events
                WHERE observation_id=?
                """,
                (observation_id,),
            ).fetchall()

            events = {}

            for row in event_rows:
                key = (
                    row["resource_type"],
                    row["resource_key"],
                    row["outcome"],
                )

                if key in events:
                    raise ProcessorError(
                        f"duplicate ZFS event {key!r}"
                    )

                events[key] = row

            differences_detected = 0
            incidents_opened = 0
            incidents_ongoing = 0
            incidents_recovered = 0

            for result in results:
                resource_type = result["resource_type"]
                resource_key = result["resource_key"]
                outcome = result["outcome"]

                open_incidents = connection.execute(
                    """
                    SELECT *
                    FROM zfs_incidents
                    WHERE resource_type=?
                      AND resource_key=?
                      AND incident_state='OPEN'
                    ORDER BY id
                    """,
                    (
                        resource_type,
                        resource_key,
                    ),
                ).fetchall()

                #
                # MATCH:
                # Resource is fully back at baseline.
                #
                if outcome == "MATCH":
                    for incident in open_incidents:
                        close_incident(
                            connection,
                            incident["id"],
                            observation_id,
                            observed_at,
                        )
                        incidents_recovered += 1

                    continue

                differences_detected += 1

                event = events.get(
                    (
                        resource_type,
                        resource_key,
                        outcome,
                    )
                )

                if event is None:
                    raise ProcessorError(
                        "missing recorded ZFS event for "
                        f"{resource_type} "
                        f"{resource_key} "
                        f"{outcome}"
                    )

                #
                # COUNTER-CHANGED:
                #
                # Permanent evidence belongs in zfs_events,
                # but the counter difference does not open
                # an incident.
                #
                # Because comparator status fields matched
                # baseline in order to reach this outcome,
                # any prior status/missing/new incident for
                # this resource has recovered.
                #
                if outcome == "COUNTER-CHANGED":
                    for incident in open_incidents:
                        close_incident(
                            connection,
                            incident["id"],
                            observation_id,
                            observed_at,
                        )
                        incidents_recovered += 1

                    continue

                if outcome not in INCIDENT_OUTCOMES:
                    raise ProcessorError(
                        f"unsupported incident outcome "
                        f"{outcome!r}"
                    )

                #
                # If the abnormal classification changed,
                # close the previous incident first.
                #
                for incident in open_incidents:
                    if (
                        incident["incident_type"]
                        == outcome
                    ):
                        continue

                    close_incident(
                        connection,
                        incident["id"],
                        observation_id,
                        observed_at,
                    )

                    incidents_recovered += 1

                current = connection.execute(
                    """
                    SELECT *
                    FROM zfs_incidents
                    WHERE resource_type=?
                      AND resource_key=?
                      AND incident_type=?
                      AND incident_state='OPEN'
                    """,
                    (
                        resource_type,
                        resource_key,
                        outcome,
                    ),
                ).fetchone()

                if current is None:
                    connection.execute(
                        """
                        INSERT INTO zfs_incidents (
                            resource_type,
                            resource_key,
                            pool_name,
                            vdev_name,
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
                            latest_changes_json,
                            note
                        )
                        VALUES (
                            ?, ?, ?, ?, ?,
                            'OPEN',
                            ?,
                            ?, ?,
                            ?, ?,
                            ?, ?,
                            1,
                            ?, ?,
                            ?
                        )
                        """,
                        (
                            resource_type,
                            resource_key,
                            result["pool_name"],
                            result["vdev_name"],
                            outcome,
                            result["baseline_state"],
                            event["id"],
                            event["id"],
                            observation_id,
                            observation_id,
                            observed_at,
                            observed_at,
                            event["changes_json"],
                            event["changes_json"],
                            (
                                "Opened automatically by "
                                "ZFS incident processor."
                            ),
                        ),
                    )

                    incidents_opened += 1

                else:
                    connection.execute(
                        """
                        UPDATE zfs_incidents
                        SET
                            baseline_state=?,
                            last_event_id=?,
                            last_abnormal_observation_id=?,
                            last_abnormal_at=?,
                            occurrence_count=
                                occurrence_count + 1,
                            latest_changes_json=?,
                            updated_at=strftime(
                                '%Y-%m-%dT%H:%M:%fZ',
                                'now'
                            )
                        WHERE id=?
                          AND incident_state='OPEN'
                        """,
                        (
                            result["baseline_state"],
                            event["id"],
                            observation_id,
                            observed_at,
                            event["changes_json"],
                            current["id"],
                        ),
                    )

                    incidents_ongoing += 1

            connection.execute(
                """
                INSERT INTO zfs_incident_processing (
                    observation_id,
                    differences_detected,
                    incidents_opened,
                    incidents_ongoing,
                    incidents_recovered,
                    note
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    differences_detected,
                    incidents_opened,
                    incidents_ongoing,
                    incidents_recovered,
                    (
                        "ZFS incident state and processing "
                        "checkpoint committed atomically."
                    ),
                ),
            )

            connection.commit()

        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise

        finally:
            connection.close()

        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "processor": "zfs_incidents",
                    "observation_id": observation_id,
                    "differences_detected":
                        differences_detected,
                    "incidents_opened":
                        incidents_opened,
                    "incidents_ongoing":
                        incidents_ongoing,
                    "incidents_recovered":
                        incidents_recovered,
                    "processing_replay": False,
                    "status": "OK",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )

    except (
        ProcessorError,
        sqlite3.Error,
    ) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
