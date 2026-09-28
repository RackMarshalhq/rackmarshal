#!/usr/bin/env python3

import fcntl
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
    incident_explainer_executable,
)

from rackmarshal.notifications.command import build_delivery_command

# Phase 2 Step 5: derive paths from config helpers (defaults = today's layout).
BASE = install_root()
PYTHON = venv_python()

def module_cmd(name):
    return [str(PYTHON), "-m", name]


COLLECTOR = module_cmd("rackmarshal.domains.ha.collector")
WRITER = module_cmd("rackmarshal.domains.ha.observation")
COMPARATOR = module_cmd("rackmarshal.domains.ha.comparator")
RECORDER = module_cmd("rackmarshal.domains.ha.events")
PROCESSOR = module_cmd("rackmarshal.domains.ha.incidents")
ENQUEUER = module_cmd("rackmarshal.notifications.queue")
DELIVERY_WORKER = module_cmd("rackmarshal.notifications.delivery")

DB = str(state_db())
HA_CREDENTIAL = str(ha_credential_file())
INCIDENT_EXPLAINER = str(incident_explainer_executable())

LOCK_FILE = Path("/run/rackmarshal/ha-cycle.lock")

SCHEMA_VERSION = 1
RUNNER = "ha_cycle"


class CycleError(RuntimeError):
    pass


def run(command, input_text=None):
    result = subprocess.run(
        [str(x) for x in command],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        raise CycleError(
            "command failed\n"
            f"command: {' '.join(str(x) for x in command)}\n"
            f"exit: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return result.stdout


def parse_json(text, stage):
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CycleError(
            f"{stage} returned invalid JSON: {exc}\n"
            f"{text}"
        ) from exc

    if not isinstance(value, dict):
        raise CycleError(
            f"{stage} did not return a JSON object"
        )

    return value


def require_nonnegative_int(obj, key, stage):
    value = obj.get(key)

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise CycleError(
            f"{stage} returned invalid {key}: "
            f"{value!r}"
        )

    return value


def database_state():
    conn = sqlite3.connect(
        f"file:{DB}?mode=ro",
        uri=True,
    )

    try:
        row = conn.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM ha_events
                ),
                (
                    SELECT COUNT(*)
                    FROM ha_incidents
                ),
                (
                    SELECT COUNT(*)
                    FROM ha_incidents
                    WHERE incident_state='OPEN'
                ),
                (
                    SELECT COUNT(*)
                    FROM incident_notifications
                    WHERE source_domain='HA'
                ),
                (
                    SELECT COALESCE(MAX(observation_id), 0)
                    FROM ha_incident_processing
                )
            """
        ).fetchone()

    finally:
        conn.close()

    return {
        "ha_events": row[0],
        "ha_incidents": row[1],
        "ha_open_incidents": row[2],
        "ha_notifications": row[3],
        "processing_checkpoint": row[4],
    }


def main():
    LOCK_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LOCK_FILE.open("w") as lock:
        try:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

        except BlockingIOError:
            print(
                json.dumps(
                    {
                        "schema_version":
                            SCHEMA_VERSION,
                        "runner":
                            RUNNER,
                        "status":
                            "SKIPPED",
                        "reason":
                            "another HA cycle is already running",
                    },
                    sort_keys=True,
                )
            )

            return 0

        before = database_state()

        #
        # 1. COLLECT
        #
        collection_text = run(COLLECTOR)

        collection = parse_json(
            collection_text,
            "HA collector",
        )

        if collection.get("collector") != \
                "home_assistant":
            raise CycleError(
                "collector identity mismatch"
            )

        if collection.get("schema_version") != \
                SCHEMA_VERSION:
            raise CycleError(
                "collector schema version mismatch"
            )

        resource_count = require_nonnegative_int(
            collection,
            "resource_count",
            "HA collector",
        )

        resources = collection.get("resources")

        if (
            not isinstance(resources, list)
            or len(resources) != resource_count
        ):
            raise CycleError(
                "collector resource_count mismatch"
            )

        #
        # 2. WRITE EXACTLY ONE OBSERVATION
        #
        writer_text = run(
            WRITER + [
            ],
            input_text=collection_text,
        )

        writer = parse_json(
            writer_text,
            "HA observation writer",
        )

        if writer.get("status") != "OK":
            raise CycleError(
                "HA writer did not report status=OK"
            )

        if writer.get("collector") != \
                "home_assistant":
            raise CycleError(
                "HA writer collector mismatch"
            )

        observation_id = writer.get(
            "observation_id"
        )

        if (
            isinstance(observation_id, bool)
            or not isinstance(observation_id, int)
            or observation_id < 1
        ):
            raise CycleError(
                "HA writer returned invalid "
                "observation_id"
            )

        if writer.get("resource_count") != \
                resource_count:
            raise CycleError(
                "HA writer resource count mismatch"
            )

        #
        # 3. COMPARE TO VERIFIED BASELINE
        #
        compare_text = run(COMPARATOR + [
            "--observation-id",
            str(observation_id),
        ])

        comparison = parse_json(
            compare_text,
            "HA comparator",
        )

        if comparison.get("observation_id") != \
                observation_id:
            raise CycleError(
                "HA comparator observation mismatch"
            )

        counts = comparison.get("counts")

        if not isinstance(counts, dict):
            raise CycleError(
                "HA comparator counts missing"
            )

        for key in (
            "MATCH",
            "STATUS-CHANGED",
            "MISSING",
            "NEW",
        ):
            require_nonnegative_int(
                counts,
                key,
                "HA comparator",
            )

        differences = (
            counts["STATUS-CHANGED"]
            + counts["MISSING"]
            + counts["NEW"]
        )

        #
        # 4. RECORD ABNORMAL EVENTS
        #
        recorder_text = run(RECORDER + [
            "--observation-id",
            str(observation_id),
        ])

        recorder = parse_json(
            recorder_text,
            "HA event recorder",
        )

        if recorder.get("observation_id") != \
                observation_id:
            raise CycleError(
                "HA event recorder observation mismatch"
            )

        if recorder.get("collector") != \
                "home_assistant":
            raise CycleError(
                "HA event recorder collector mismatch"
            )

        recorded_differences = require_nonnegative_int(
            recorder,
            "differences",
            "HA event recorder",
        )

        if recorded_differences != differences:
            raise CycleError(
                "HA recorder/comparator difference "
                "count mismatch"
            )

        events_inserted = require_nonnegative_int(
            recorder,
            "events_inserted",
            "HA event recorder",
        )

        events_existing = require_nonnegative_int(
            recorder,
            "events_existing",
            "HA event recorder",
        )

        #
        # 5. ADVANCE INCIDENT PROCESSING CHECKPOINT
        #
        processor_text = run(PROCESSOR)

        processor = parse_json(
            processor_text,
            "HA incident processor",
        )

        if processor.get("status") == \
                "NO-NEW-OBSERVATION":
            raise CycleError(
                "HA processor did not consume "
                "the newly written observation"
            )

        if processor.get("observation_id") != \
                observation_id:
            raise CycleError(
                "HA incident processor consumed "
                "unexpected observation "
                f"{processor.get('observation_id')!r}; "
                f"expected {observation_id}"
            )

        processed_differences = require_nonnegative_int(
            processor,
            "differences_detected",
            "HA incident processor",
        )

        if processed_differences != differences:
            raise CycleError(
                "HA processor/comparator difference "
                "count mismatch"
            )

        incidents_opened = require_nonnegative_int(
            processor,
            "incidents_opened",
            "HA incident processor",
        )

        incidents_ongoing = require_nonnegative_int(
            processor,
            "incidents_ongoing",
            "HA incident processor",
        )

        incidents_recovered = require_nonnegative_int(
            processor,
            "incidents_recovered",
            "HA incident processor",
        )

        #
        # 6. ENQUEUE DETERMINISTIC NOTIFICATIONS
        #
        enqueuer_text = run(ENQUEUER + [
            "--db",
            DB,
        ])

        enqueuer = parse_json(
            enqueuer_text,
            "notification enqueuer",
        )

        if enqueuer.get("schema_version") != \
                SCHEMA_VERSION:
            raise CycleError(
                "notification enqueuer schema mismatch"
            )

        if enqueuer.get("consumer") != \
                "incident_notification_enqueuer":
            raise CycleError(
                "notification enqueuer identity mismatch"
            )

        if enqueuer.get("status") != "OK":
            raise CycleError(
                "notification enqueuer did not "
                "report status=OK"
            )

        notifications_inserted = \
            require_nonnegative_int(
                enqueuer,
                "notifications_inserted",
                "notification enqueuer",
            )

        incidents_scanned = \
            require_nonnegative_int(
                enqueuer,
                "incidents_scanned",
                "notification enqueuer",
            )

        #
        # 7. DELIVER PENDING/RETRYABLE NOTIFICATIONS
        #
        delivery_text = run(build_delivery_command(
            DELIVERY_WORKER, DB, HA_CREDENTIAL, INCIDENT_EXPLAINER
        ))

        delivery = parse_json(
            delivery_text,
            "notification delivery worker",
        )

        if delivery.get("schema_version") != \
                SCHEMA_VERSION:
            raise CycleError(
                "delivery worker schema mismatch"
            )

        if delivery.get("worker") != \
                "incident_notification_delivery_worker":
            raise CycleError(
                "delivery worker identity mismatch"
            )

        if delivery.get("status") != "OK":
            raise CycleError(
                "delivery worker did not report "
                "status=OK"
            )

        delivery_counts = {}

        for key in (
            "rows_scanned",
            "sent",
            "failed",
            "fallback_deliveries",
        ):
            delivery_counts[key] = \
                require_nonnegative_int(
                    delivery,
                    key,
                    "notification delivery worker",
                )

        after = database_state()

        if after["processing_checkpoint"] != \
                observation_id:
            raise CycleError(
                "HA processing checkpoint does not "
                "match newly processed observation"
            )

        summary = {
            "schema_version":
                SCHEMA_VERSION,
            "runner":
                RUNNER,
            "status":
                "OK",
            "observation_id":
                observation_id,
            "resource_count":
                resource_count,
            "comparison_counts":
                counts,
            "differences":
                differences,
            "events": {
                "inserted":
                    events_inserted,
                "existing":
                    events_existing,
            },
            "incidents": {
                "opened":
                    incidents_opened,
                "ongoing":
                    incidents_ongoing,
                "recovered":
                    incidents_recovered,
            },
            "notifications": {
                "incidents_scanned":
                    incidents_scanned,
                "inserted":
                    notifications_inserted,
                "delivery":
                    delivery_counts,
            },
            "database_before":
                before,
            "database_after":
                after,
        }

        print(
            json.dumps(
                summary,
                indent=2,
                sort_keys=True,
            )
        )

        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())

    except (
        CycleError,
        sqlite3.Error,
    ) as exc:
        print(
            json.dumps(
                {
                    "schema_version":
                        SCHEMA_VERSION,
                    "runner":
                        RUNNER,
                    "status":
                        "FAILED",
                    "error":
                        str(exc),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )

        raise SystemExit(1)
