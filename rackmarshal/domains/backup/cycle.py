#!/usr/bin/env python3

import json
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

# Phase 2 Step 6: derive paths from config helpers (defaults = today's layout).
BASE = install_root()
PYTHON = venv_python()

def module_cmd(name):
    return [str(PYTHON), "-m", name]


COLLECTOR = module_cmd("rackmarshal.domains.backup.collector")
WRITER = module_cmd("rackmarshal.domains.backup.observation")
COMPARATOR = module_cmd("rackmarshal.domains.backup.comparator")
RECORDER = module_cmd("rackmarshal.domains.backup.events")
PROCESSOR = module_cmd("rackmarshal.domains.backup.incidents")
ENQUEUER = module_cmd("rackmarshal.notifications.queue")
DELIVERY_WORKER = module_cmd("rackmarshal.notifications.delivery")

DB = str(state_db())
HA_CREDENTIAL = str(ha_credential_file())
INCIDENT_EXPLAINER = str(incident_explainer_executable())


def run(command, input_text=None):
    result = subprocess.run(
        [str(x) for x in command],
        input=input_text,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")

        raise RuntimeError(
            f"command failed with exit code "
            f"{result.returncode}: "
            + " ".join(str(x) for x in command)
        )

    return result.stdout


def parse_json(text, stage):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{stage} returned invalid JSON: {exc}"
        ) from exc


def enqueue_notifications():
    text = run(ENQUEUER + [
        "--db",
        DB,
    ])

    result = parse_json(
        text,
        "notification enqueuer",
    )

    if result.get("schema_version") != 1:
        raise RuntimeError(
            "unexpected notification enqueuer schema"
        )

    if (
        result.get("consumer")
        != "incident_notification_enqueuer"
    ):
        raise RuntimeError(
            "unexpected notification enqueuer identity"
        )

    if result.get("status") != "OK":
        raise RuntimeError(
            "notification enqueuer did not report status=OK"
        )

    for key in (
        "incidents_scanned",
        "notifications_inserted",
    ):
        value = result.get(key)

        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise RuntimeError(
                f"notification enqueuer returned invalid {key}"
            )

    return result


def deliver_notifications():
    text = run(build_delivery_command(
        DELIVERY_WORKER, DB, HA_CREDENTIAL, INCIDENT_EXPLAINER
    ))

    result = parse_json(
        text,
        "notification delivery worker",
    )

    if result.get("schema_version") != 1:
        raise RuntimeError(
            "unexpected delivery worker schema"
        )

    if (
        result.get("worker")
        != "incident_notification_delivery_worker"
    ):
        raise RuntimeError(
            "unexpected delivery worker identity"
        )

    if result.get("status") != "OK":
        raise RuntimeError(
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
            raise RuntimeError(
                f"delivery worker returned invalid {key}"
            )

    return result


def main():
    #
    # 1. Collect current PVE + PBS state.
    #
    collection_text = run(COLLECTOR)

    collection = parse_json(
        collection_text,
        "collector",
    )

    if collection.get("collector") != "backup_domain":
        raise RuntimeError(
            "collector identity mismatch"
        )

    if collection.get("tls_verified") is not True:
        raise RuntimeError(
            "collector did not report verified TLS"
        )

    #
    # 2. Persist exactly one observation.
    #
    writer_text = run(
        WRITER,
        input_text=collection_text,
    )

    writer = parse_json(
        writer_text,
        "writer",
    )

    if writer.get("status") != "recorded":
        raise RuntimeError(
            f"writer did not record observation: {writer}"
        )

    observation_id = writer.get("observation_id")

    if (
        isinstance(observation_id, bool)
        or not isinstance(observation_id, int)
        or observation_id < 1
    ):
        raise RuntimeError(
            f"invalid observation_id from writer: "
            f"{observation_id!r}"
        )

    #
    # 3. Compare new observation to verified baseline.
    #
    comparison_text = run(COMPARATOR + [
        "--observation-id",
        str(observation_id),
    ])

    comparison = parse_json(
        comparison_text,
        "comparator",
    )

    if comparison.get("comparator") != "backup_baseline":
        raise RuntimeError(
            "comparator identity mismatch"
        )

    if comparison.get("observation_id") != observation_id:
        raise RuntimeError(
            "comparator observation mismatch"
        )

    #
    # 4. Persist abnormal events, if any.
    #
    recorder_text = run(
        RECORDER,
        input_text=comparison_text,
    )

    recorder = parse_json(
        recorder_text,
        "event recorder",
    )

    if recorder.get("status") != "OK":
        raise RuntimeError(
            f"event recorder failed: {recorder}"
        )

    #
    # 5. Open/update/recover incidents.
    #
    processor_text = run(
        PROCESSOR,
        input_text=comparison_text,
    )

    processor = parse_json(
        processor_text,
        "incident processor",
    )

    if processor.get("status") not in {
        "OK",
        "REPLAY",
    }:
        raise RuntimeError(
            f"incident processor failed: {processor}"
        )

    #
    # 6. Enqueue deterministic incident notifications.
    #
    notification_result = enqueue_notifications()

    #
    # 7. Deliver pending/retryable notifications to HA.
    #
    delivery_result = deliver_notifications()

    summary = {
        "schema_version": 1,
        "runner": "backup_cycle",
        "status": "OK",
        "observation_id": observation_id,
        "resource_count":
            collection.get("resource_count"),
        "comparison_counts":
            comparison.get("counts"),
        "events": {
            "candidate":
                recorder.get("candidate_events"),
            "inserted":
                recorder.get("inserted"),
            "duplicates":
                recorder.get("duplicates"),
        },
        "incidents": {
            "differences_detected":
                processor.get(
                    "differences_detected"
                ),
            "opened":
                processor.get(
                    "incidents_opened"
                ),
            "ongoing":
                processor.get(
                    "incidents_ongoing"
                ),
            "recovered":
                processor.get(
                    "incidents_recovered"
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
                delivery_result.get(
                    "rows_scanned"
                ),
            "sent":
                delivery_result.get(
                    "sent"
                ),
            "failed":
                delivery_result.get(
                    "failed"
                ),
            "fallback_deliveries":
                delivery_result.get(
                    "fallback_deliveries"
                ),
        },
    }

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "backup_cycle",
                    "status": "ERROR",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
