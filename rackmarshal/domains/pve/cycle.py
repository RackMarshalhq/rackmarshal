#!/usr/bin/env python3

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from rackmarshal.core.config import (
    state_db,
    install_root,
    venv_python,
    ha_credential_file,
)

# Phase 2 Step 3: derive paths from config helpers (defaults = today's layout).
_ROOT = install_root()
PYTHON = str(venv_python())

def module_cmd(name):
    return [str(PYTHON), "-m", name]

COLLECTOR = module_cmd("rackmarshal.domains.pve.collector")
WRITER = module_cmd("rackmarshal.domains.pve.observation")
COMPARATOR = module_cmd("rackmarshal.domains.pve.comparator")
RECORDER = module_cmd("rackmarshal.domains.pve.events")
PROCESSOR = module_cmd("rackmarshal.domains.pve.incidents")
ENQUEUER = module_cmd("rackmarshal.notifications.queue")
DELIVERY_WORKER = module_cmd("rackmarshal.notifications.delivery")
HA_CREDENTIAL = str(ha_credential_file())
INCIDENT_EXPLAINER = module_cmd("rackmarshal.incidents.explain")

DB = str(state_db())

SCHEMA_VERSION = 1
ORCHESTRATOR_NAME = "pve_cycle"


class CycleError(Exception):
    pass


def run_json(command, *, stdin_text=None):
    result = subprocess.run(
        command,
        input=stdin_text,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()

        detail = stderr or stdout or (
            f"command exited with status {result.returncode}"
        )

        raise CycleError(detail)

    output = result.stdout.strip()

    if not output:
        raise CycleError(
            f"command produced no JSON output: {command}"
        )

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise CycleError(
            f"invalid JSON from {command}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise CycleError(
            f"expected JSON object from {command}"
        )

    return data


def collect():
    return run_json(
        COLLECTOR
    )


def write_observation(observation):
    payload = json.dumps(
        observation,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    result = run_json(
        WRITER,
        stdin_text=payload,
    )

    if result.get("status") != "written":
        raise CycleError(
            "observation writer did not report status=written"
        )

    observation_id = result.get("observation_id")

    if (
        not isinstance(observation_id, int)
        or isinstance(observation_id, bool)
        or observation_id <= 0
    ):
        raise CycleError(
            f"invalid observation_id: {observation_id!r}"
        )

    return result


def compare(observation_id):
    result = run_json(
        COMPARATOR + [
            "--observation-id",
            str(observation_id),
        ]
    )

    if result.get("schema_version") != SCHEMA_VERSION:
        raise CycleError(
            "unexpected comparator schema version"
        )

    if result.get("comparator") != "pve_resource_baseline":
        raise CycleError(
            "unexpected comparator identity"
        )

    if result.get("observation_id") != observation_id:
        raise CycleError(
            "comparator observation ID mismatch"
        )

    return result


def record_events(observation_id):
    result = run_json(
        RECORDER + [
            "--observation-id",
            str(observation_id),
        ]
    )

    if result.get("schema_version") != SCHEMA_VERSION:
        raise CycleError(
            "unexpected event recorder schema version"
        )

    if result.get("recorder") != "pve_resource_events":
        raise CycleError(
            "unexpected event recorder identity"
        )

    if result.get("observation_id") != observation_id:
        raise CycleError(
            "event recorder observation ID mismatch"
        )

    return result


def process_incidents(observation_id):
    result = run_json(
        PROCESSOR + [
            "--observation-id",
            str(observation_id),
        ]
    )

    if result.get("schema_version") != SCHEMA_VERSION:
        raise CycleError(
            "unexpected incident processor schema version"
        )

    if result.get("processor") != "pve_resource_incidents":
        raise CycleError(
            "unexpected incident processor identity"
        )

    if result.get("observation_id") != observation_id:
        raise CycleError(
            "incident processor observation ID mismatch"
        )

    return result


def enqueue_notifications():
    result = run_json(
        ENQUEUER + [
            "--db",
            DB,
        ]
    )

    if result.get("schema_version") != SCHEMA_VERSION:
        raise CycleError(
            "unexpected notification enqueuer schema version"
        )

    if (
        result.get("consumer")
        != "incident_notification_enqueuer"
    ):
        raise CycleError(
            "unexpected notification enqueuer identity"
        )

    if result.get("status") != "OK":
        raise CycleError(
            "notification enqueuer did not report status=OK"
        )

    inserted = result.get("notifications_inserted")
    scanned = result.get("incidents_scanned")

    if (
        isinstance(inserted, bool)
        or not isinstance(inserted, int)
        or inserted < 0
    ):
        raise CycleError(
            "notification enqueuer returned invalid "
            "notifications_inserted"
        )

    if (
        isinstance(scanned, bool)
        or not isinstance(scanned, int)
        or scanned < 0
    ):
        raise CycleError(
            "notification enqueuer returned invalid "
            "incidents_scanned"
        )

    return result



def deliver_notifications():
    result = run_json(
        DELIVERY_WORKER + [
            "--db",
            DB,
            "--credential",
            HA_CREDENTIAL,
            "--explainer",
            INCIDENT_EXPLAINER,
            "--notification-prefix",
            "rackmarshal",
        ]
    )

    if result.get("schema_version") != SCHEMA_VERSION:
        raise CycleError(
            "unexpected delivery worker schema version"
        )

    if (
        result.get("worker")
        != "incident_notification_delivery_worker"
    ):
        raise CycleError(
            "unexpected delivery worker identity"
        )

    if result.get("status") != "OK":
        raise CycleError(
            "delivery worker did not report status=OK"
        )

    for key in (
        "rows_scanned",
        "sent",
        "failed",
        "fallback_deliveries",
    ):
        value = result.get(key)

        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise CycleError(
                f"delivery worker returned invalid {key}"
            )

    return result

def get_database_state():
    if not Path(DB).is_file():
        raise CycleError(
            f"database not found: {DB}"
        )

    connection = sqlite3.connect(
        f"file:{DB}?mode=ro",
        uri=True,
    )

    try:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM observations),
                (SELECT COUNT(*) FROM resource_events),
                (SELECT COUNT(*) FROM resource_incidents),
                (
                    SELECT COUNT(*)
                    FROM resource_incidents
                    WHERE incident_state = 'OPEN'
                )
            """
        ).fetchone()

    finally:
        connection.close()

    return {
        "observations": row[0],
        "resource_events": row[1],
        "resource_incidents": row[2],
        "open_incidents": row[3],
    }


def main():
    try:
        database_before = get_database_state()

        observation = collect()

        write_result = write_observation(
            observation
        )

        observation_id = write_result[
            "observation_id"
        ]

        comparison = compare(
            observation_id
        )

        event_result = record_events(
            observation_id
        )

        incident_result = process_incidents(
            observation_id
        )

        notification_result = enqueue_notifications()
        delivery_result = deliver_notifications()

        database_after = get_database_state()

        output = {
            "schema_version": SCHEMA_VERSION,
            "orchestrator": ORCHESTRATOR_NAME,
            "status": "complete",
            "observation_id": observation_id,
            "observed_at": observation.get(
                "observed_at"
            ),
            "resource_count": observation.get(
                "resource_count"
            ),
            "tls_verified": observation.get(
                "tls_verified"
            ),
            "comparison_summary": comparison.get(
                "summary"
            ),
            "events": {
                "differences_detected":
                    event_result.get(
                        "differences_detected"
                    ),
                "inserted":
                    event_result.get(
                        "events_inserted"
                    ),
                "already_recorded":
                    event_result.get(
                        "events_already_recorded"
                    ),
            },
            "incidents": {
                "differences_detected":
                    incident_result.get(
                        "differences_detected"
                    ),
                "opened":
                    incident_result.get(
                        "incidents_opened"
                    ),
                "ongoing":
                    incident_result.get(
                        "incidents_ongoing"
                    ),
                "recovered":
                    incident_result.get(
                        "incidents_recovered"
                    ),
                "already_processed":
                    incident_result.get(
                        "incidents_already_processed"
                    ),
            },
            "notifications": {
                "incidents_scanned":
                    notification_result.get(
                        "incidents_scanned"
                    ),
                "inserted":
                    notification_result.get(
                        "notifications_inserted"
                    ),
            },
            "delivery": {
                "rows_scanned":
                    delivery_result.get("rows_scanned"),
                "sent":
                    delivery_result.get("sent"),
                "failed":
                    delivery_result.get("failed"),
                "fallback_deliveries":
                    delivery_result.get(
                        "fallback_deliveries"
                    ),
            },
            "database_before": database_before,
            "database_after": database_after,
        }

        print(
            json.dumps(
                output,
                indent=2,
                sort_keys=False,
            )
        )

        return 0

    except (
        CycleError,
        OSError,
        sqlite3.Error,
    ) as exc:
        print(
            json.dumps(
                {
                    "schema_version":
                        SCHEMA_VERSION,
                    "orchestrator":
                        ORCHESTRATOR_NAME,
                    "status":
                        "failed",
                    "error":
                        str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
