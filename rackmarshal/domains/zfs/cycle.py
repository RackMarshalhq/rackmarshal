#!/usr/bin/env python3

import json
import subprocess
import sys
import fcntl
from pathlib import Path

from rackmarshal.core.config import (
    state_db,
    install_root,
    ha_credential_file,
)

# Phase 2 Step 4: derive paths from config helpers (defaults = today's layout).
_ROOT = install_root()
DB = str(state_db())
PYTHON = sys.executable

def module_cmd(name):
    return [PYTHON, "-m", name]


COLLECTOR = module_cmd("rackmarshal.domains.zfs.collector")
WRITER = module_cmd("rackmarshal.domains.zfs.observation")
COMPARATOR = module_cmd("rackmarshal.domains.zfs.comparator")
RECORDER = module_cmd("rackmarshal.domains.zfs.events")
PROCESSOR = module_cmd("rackmarshal.domains.zfs.incidents")
ENQUEUER = module_cmd("rackmarshal.notifications.queue")
DELIVERY_WORKER = module_cmd("rackmarshal.notifications.delivery")
HA_CREDENTIAL = str(ha_credential_file())
INCIDENT_EXPLAINER = module_cmd("rackmarshal.incidents.explain")

LOCK_FILE = Path("/run/lock/rackmarshal-zfs-cycle.lock")


class CycleError(Exception):
    pass


def run(command, stdin_text=None):
    result = subprocess.run(
        command,
        input=stdin_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        message = (
            f"command failed: {' '.join(command)}\n"
            f"exit={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        raise CycleError(message)

    return result.stdout


def parse_json(text, stage):
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CycleError(
            f"{stage} returned invalid JSON: {exc}\n{text}"
        ) from exc

    if not isinstance(value, dict):
        raise CycleError(
            f"{stage} did not return a JSON object"
        )

    return value


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
                        "cycle": "zfs",
                        "status": "SKIPPED",
                        "reason":
                            "another ZFS cycle is already running",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return

        #
        # 1. COLLECT
        #
        collected_text = run(COLLECTOR)
        collected = parse_json(
            collected_text,
            "collector",
        )

        if collected.get("collector") != "zfs_status":
            raise CycleError(
                "unexpected collector identity"
            )

        #
        # 2. WRITE OBSERVATION
        #
        writer_text = run(
            WRITER,
            stdin_text=collected_text,
        )

        writer = parse_json(
            writer_text,
            "writer",
        )

        if writer.get("writer") != "zfs_observation":
            raise CycleError(
                "unexpected writer identity"
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
                "writer returned invalid observation_id"
            )

        #
        # 3. COMPARE
        #
        compare_text = run(
            
                COMPARATOR + [
                "--database",
                DB,
                "--observation-id",
                str(observation_id),
            ]
        )

        comparison = parse_json(
            compare_text,
            "comparator",
        )

        if (
            comparison.get("comparator")
            != "zfs_baseline"
        ):
            raise CycleError(
                "unexpected comparator identity"
            )

        if (
            comparison.get("observation_id")
            != observation_id
        ):
            raise CycleError(
                "comparator observation mismatch"
            )

        #
        # 4. RECORD EVENTS
        #
        recorder_text = run(
            
                RECORDER + [
                "--database",
                DB,
            ],
            stdin_text=compare_text,
        )

        recorder = parse_json(
            recorder_text,
            "event recorder",
        )

        if recorder.get("recorder") != "zfs_events":
            raise CycleError(
                "unexpected event recorder identity"
            )

        if (
            recorder.get("observation_id")
            != observation_id
        ):
            raise CycleError(
                "event recorder observation mismatch"
            )

        #
        # 5. PROCESS INCIDENTS
        #
        processor_text = run(
            
                PROCESSOR + [
                "--database",
                DB,
            ],
            stdin_text=compare_text,
        )

        processor = parse_json(
            processor_text,
            "incident processor",
        )

        if (
            processor.get("processor")
            != "zfs_incidents"
        ):
            raise CycleError(
                "unexpected incident processor identity"
            )

        if (
            processor.get("observation_id")
            != observation_id
        ):
            raise CycleError(
                "incident processor observation mismatch"
            )

        #
        # 6. ENQUEUE INCIDENT NOTIFICATIONS
        #
        enqueuer_text = run(
            
                ENQUEUER + [
                "--db",
                DB,
            ]
        )

        enqueuer = parse_json(
            enqueuer_text,
            "notification enqueuer",
        )

        if (
            enqueuer.get("consumer")
            != "incident_notification_enqueuer"
        ):
            raise CycleError(
                "unexpected notification enqueuer identity"
            )

        if enqueuer.get("schema_version") != 1:
            raise CycleError(
                "unexpected notification enqueuer schema"
            )

        if enqueuer.get("status") != "OK":
            raise CycleError(
                "notification enqueuer did not report status=OK"
            )

        notifications_inserted = enqueuer.get(
            "notifications_inserted"
        )

        incidents_scanned = enqueuer.get(
            "incidents_scanned"
        )

        if (
            isinstance(notifications_inserted, bool)
            or not isinstance(notifications_inserted, int)
            or notifications_inserted < 0
        ):
            raise CycleError(
                "notification enqueuer returned invalid "
                "notifications_inserted"
            )

        if (
            isinstance(incidents_scanned, bool)
            or not isinstance(incidents_scanned, int)
            or incidents_scanned < 0
        ):
            raise CycleError(
                "notification enqueuer returned invalid "
                "incidents_scanned"
            )

        #
        # 7. DELIVER INCIDENT NOTIFICATIONS
        #
        delivery_text = run(
            
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

        delivery = parse_json(
            delivery_text,
            "notification delivery worker",
        )

        if (
            delivery.get("worker")
            != "incident_notification_delivery_worker"
        ):
            raise CycleError(
                "unexpected delivery worker identity"
            )

        if delivery.get("schema_version") != 1:
            raise CycleError(
                "unexpected delivery worker schema"
            )

        if delivery.get("status") != "OK":
            raise CycleError(
                "delivery worker did not report status=OK"
            )

        for key in (
            "rows_scanned",
            "sent",
            "failed",
            "fallback_deliveries",
        ):
            value = delivery.get(key)

            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise CycleError(
                    "delivery worker returned invalid "
                    + key
                )

        #
        # Final concise cycle result.
        #
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "cycle": "zfs",
                    "status": "OK",
                    "observation_id": observation_id,
                    "observed_at":
                        collected.get("observed_at"),
                    "pool_count":
                        collected.get("pool_count"),
                    "comparison_counts":
                        comparison.get("counts"),
                    "events_inserted":
                        recorder.get("inserted"),
                    "event_duplicates":
                        recorder.get("duplicates"),
                    "incidents_opened":
                        processor.get(
                            "incidents_opened"
                        ),
                    "incidents_ongoing":
                        processor.get(
                            "incidents_ongoing"
                        ),
                    "incidents_recovered":
                        processor.get(
                            "incidents_recovered"
                        ),
                    "notifications":
                        {
                            "incidents_scanned":
                                incidents_scanned,
                            "inserted":
                                notifications_inserted,
                        },
                    "delivery": {
                        "rows_scanned":
                            delivery.get("rows_scanned"),
                        "sent":
                            delivery.get("sent"),
                        "failed":
                            delivery.get("failed"),
                        "fallback_deliveries":
                            delivery.get(
                                "fallback_deliveries"
                            ),
                    },
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    try:
        main()

    except CycleError as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "cycle": "zfs",
                    "status": "ERROR",
                    "error": str(exc),
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
