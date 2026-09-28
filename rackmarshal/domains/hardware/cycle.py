#!/usr/bin/env python3

import fcntl
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rackmarshal.core.config import (
    load_config,
    require,
    state_db,
    install_root,
    venv_python,
    ha_credential_file,
    incident_explainer_executable,
)

from rackmarshal.notifications.command import build_delivery_command


CONFIG = load_config()

SITE_NAME = require(
    CONFIG,
    "SITE_NAME",
)

DB = str(state_db(CONFIG))
# Phase 2 Step 7: path helpers only — thresholds/notify behavior unchanged.
_ROOT = install_root()
PYTHON = str(venv_python())

def module_cmd(name):
    return [str(PYTHON), "-m", name]

COLLECTOR = module_cmd("rackmarshal.domains.hardware.collector")
PROCESS_HARDWARE_INCIDENTS = module_cmd("rackmarshal.domains.hardware.incidents")
ENQUEUER = module_cmd("rackmarshal.notifications.queue")
DELIVERY_WORKER = module_cmd("rackmarshal.notifications.delivery")
HA_CREDENTIAL = str(ha_credential_file())
INCIDENT_EXPLAINER = str(incident_explainer_executable())
LOCK_FILE = Path("/run/rackmarshal/hardware-cycle.lock")

# Production thresholds.
#
# A healthy post-repair full backupssd scrub reached about 74 C.
# Therefore 70 C is NOT an incident threshold.
#
HOT_THRESHOLD = float(require(CONFIG, "HARDWARE_HOT_THRESHOLD_C"))
HOT_REQUIRED_SAMPLES = int(require(CONFIG, "HARDWARE_HOT_REQUIRED_SAMPLES"))

URGENT_THRESHOLD = float(require(CONFIG, "HARDWARE_URGENT_THRESHOLD_C"))

RECOVERY_THRESHOLD = float(require(CONFIG, "HARDWARE_RECOVERY_THRESHOLD_C"))
RECOVERY_REQUIRED_SAMPLES = int(require(CONFIG, "HARDWARE_RECOVERY_REQUIRED_SAMPLES"))


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def emit(value):
    print(
        json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
        )
    )



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
        raise RuntimeError(detail)

    output = result.stdout.strip()
    if not output:
        raise RuntimeError(
            f"command produced no JSON output: {command}"
        )

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"invalid JSON from {command}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"expected JSON object from {command}"
        )

    return data



def process_hardware_incidents_ledger():
    """Step D: mirror temperature events into hardware_events/incidents."""
    # PROCESS_HARDWARE_INCIDENTS is an argv command produced by module_cmd().
    # Execute it directly; treating it as a filesystem path breaks packaged installs.
    result = subprocess.run(
        PROCESS_HARDWARE_INCIDENTS,
        text=True,
        cwd=str(_ROOT),
        check=False,
        capture_output=True,
    )
    text = (result.stdout or "").strip()
    if text:
        print(text)
    if result.stderr:
        sys.stderr.write(result.stderr)
        if not result.stderr.endswith("\n"):
            sys.stderr.write("\n")
    if result.returncode != 0:
        raise SystemExit(
            f"process_hardware_incidents failed rc={result.returncode}"
        )
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
    except Exception:
        pass
    return {"status": "OK", "note": "no_json"}


def enqueue_notifications():
    """Shared path: build/enqueue HARDWARE (+other) pending notifications."""
    result = run_json(
        ENQUEUER + [
            "--db",
            DB,
        ]
    )

    if result.get("schema_version") != 1:
        raise RuntimeError(
            "unexpected notification enqueuer schema version"
        )

    if result.get("consumer") != "incident_notification_enqueuer":
        raise RuntimeError(
            "unexpected notification enqueuer identity"
        )

    if result.get("status") != "OK":
        raise RuntimeError(
            "notification enqueuer did not report status=OK"
        )

    return result


def deliver_notifications():
    """Shared path: deliver PENDING incident_notifications via HA."""
    result = run_json(
        build_delivery_command(
            DELIVERY_WORKER, DB, HA_CREDENTIAL, INCIDENT_EXPLAINER
        )
    )

    if result.get("schema_version") != 1:
        raise RuntimeError(
            "unexpected delivery worker schema version"
        )

    if result.get("worker") != "incident_notification_delivery_worker":
        raise RuntimeError(
            "unexpected delivery worker identity"
        )

    if result.get("status") != "OK":
        raise RuntimeError(
            "delivery worker did not report status=OK"
        )

    return result


def collect():
    result = subprocess.run(
        COLLECTOR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"collector failed exit={result.returncode}: "
            f"{result.stderr.strip()}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"collector returned invalid JSON: {exc}"
        )

    if payload.get("collector") != "hardware_temperature":
        raise RuntimeError("unexpected collector identity")

    return payload


def initialize_db(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hardware_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            host TEXT NOT NULL,
            serial TEXT NOT NULL,
            model TEXT,
            role TEXT NOT NULL,
            nvme TEXT,
            temperature_c REAL,
            present INTEGER NOT NULL
                CHECK (present IN (0,1)),
            status TEXT NOT NULL
                CHECK (
                    status IN (
                        'OK',
                        'HOT',
                        'URGENT',
                        'MISSING'
                    )
                ),
            recorded_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ','now')
            )
        );

        CREATE INDEX IF NOT EXISTS
        idx_hardware_observations_serial_time
        ON hardware_observations(
            serial,
            observed_at
        );
"""
    )


def write_observations(conn, payload, observed_at, devices):
    """Step F: facts only — compare/streaks live in process_hardware_incidents."""
    counts = {"OK": 0, "HOT": 0, "URGENT": 0, "MISSING": 0}
    for device in devices:
        serial = device["serial"]
        model = device.get("model") or device["expected_model"]
        role = device["role"]
        nvme = device.get("nvme")
        present = bool(device.get("present"))
        temp = device.get("temperature_c")

        if not present or temp is None:
            sample_status = "MISSING"
        elif temp >= URGENT_THRESHOLD:
            sample_status = "URGENT"
        elif temp >= HOT_THRESHOLD:
            sample_status = "HOT"
        else:
            sample_status = "OK"
        counts[sample_status] += 1

        conn.execute(
            """
            INSERT INTO hardware_observations (
                observed_at, host, serial, model, role, nvme,
                temperature_c, present, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observed_at,
                payload.get("host", SITE_NAME),
                serial,
                model,
                role,
                nvme,
                temp,
                1 if present else 0,
                sample_status,
            ),
        )
    return counts


def main():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    with LOCK_FILE.open("w") as lock:
        try:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            emit(
                {
                    "runner": "hardware_cycle",
                    "status": "SKIPPED",
                    "reason": "another hardware cycle is running",
                }
            )
            return

        payload = collect()
        observed_at = payload.get("observed_at") or utcnow()
        devices = payload.get("devices", [])
        if not isinstance(devices, list):
            raise RuntimeError("devices is not an array")

        conn = sqlite3.connect(DB, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            initialize_db(conn)
            counts = write_observations(conn, payload, observed_at, devices)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        # Step F: process owns compare/streaks/events/incidents
        ledger_result = process_hardware_incidents_ledger()
        notification_result = enqueue_notifications()
        delivery_result = deliver_notifications()

        emit(
            {
                "runner": "hardware_cycle",
                "schema_version": 1,
                "status": "OK",
                "observed_at": observed_at,
                "device_count": len(devices),
                "samples": counts,
                "incidents": {
                    "opened": ledger_result.get("opened", 0),
                    "escalated": ledger_result.get("escalated", 0),
                    "recovered": ledger_result.get("recovered", 0),
                },
                "ledger": ledger_result,
                "notifications": {
                    "inserted": notification_result.get(
                        "notifications_inserted"
                    ),
                    "scanned": notification_result.get(
                        "incidents_scanned"
                    ),
                },
                "delivery": {
                    "rows_scanned": delivery_result.get(
                        "rows_scanned"
                    ),
                    "sent": delivery_result.get("sent"),
                    "failed": delivery_result.get("failed"),
                    "fallback_deliveries": delivery_result.get(
                        "fallback_deliveries"
                    ),
                },
            }
        )


if __name__ == "__main__":
    main()
