#!/usr/bin/env python3

import json
import subprocess
import sys

from rackmarshal.core.config import (
    load_config,
    require,
)


CONFIG = load_config()

SITE_NAME = require(
    CONFIG,
    "SITE_NAME",
)

SSH_HOST = require(
    CONFIG,
    "HARDWARE_SSH_HOST",
)

SSH_USER = require(
    CONFIG,
    "HARDWARE_SSH_USER",
)

SSH_KEY = require(
    CONFIG,
    "HARDWARE_SSH_KEY",
)

KNOWN_HOSTS = require(
    CONFIG,
    "HARDWARE_KNOWN_HOSTS",
)

NVME_SERIALS = [
    serial.strip()
    for serial in require(
        CONFIG,
        "HARDWARE_NVME_SERIALS",
    ).split(",")
    if serial.strip()
]

if not NVME_SERIALS:
    raise RuntimeError(
        "HARDWARE_NVME_SERIALS contains no device serials"
    )

if len(NVME_SERIALS) != len(set(NVME_SERIALS)):
    raise RuntimeError(
        "HARDWARE_NVME_SERIALS contains duplicate serials"
    )

EXPECTED = {
    serial: {
        "model": require(
            CONFIG,
            f"HARDWARE_NVME_{serial}_MODEL",
        ),
        "role": require(
            CONFIG,
            f"HARDWARE_NVME_{serial}_ROLE",
        ),
    }
    for serial in NVME_SERIALS
}


def fail(message):
    print(
        json.dumps(
            {
                "schema_version": 1,
                "collector": "hardware_temperature",
                "status": "ERROR",
                "error": message,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    raise SystemExit(1)


def main():
    cmd = [
        "/usr/bin/ssh",
        "-i", SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10",
        f"{SSH_USER}@{SSH_HOST}",
        "ignored",
    ]

    try:
        result = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        fail(f"SSH collection failed: {exc}")

    if result.returncode != 0:
        fail(
            f"SSH collection exit={result.returncode}: "
            f"{result.stderr.strip()}"
        )

    try:
        source = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"host observer returned invalid JSON: {exc}")

    if source.get("collector") != "nvme_temperature":
        fail("unexpected host collector identity")

    raw_devices = source.get("devices")

    if not isinstance(raw_devices, list):
        fail("host observer devices is not an array")

    seen = {}
    devices = []

    for raw in raw_devices:
        if not isinstance(raw, dict):
            continue

        serial = raw.get("serial")

        if serial not in EXPECTED:
            continue

        temp = raw.get("temperature_c")

        if not isinstance(temp, (int, float)) or isinstance(temp, bool):
            temp = None

        expected = EXPECTED[serial]

        device = {
            "serial": serial,
            "model": raw.get("model"),
            "expected_model": expected["model"],
            "role": expected["role"],
            "nvme": raw.get("nvme"),
            "temperature_c": temp,
            "present": True,
        }

        seen[serial] = True
        devices.append(device)

    for serial, expected in EXPECTED.items():
        if serial in seen:
            continue

        devices.append(
            {
                "serial": serial,
                "model": None,
                "expected_model": expected["model"],
                "role": expected["role"],
                "nvme": None,
                "temperature_c": None,
                "present": False,
            }
        )

    devices.sort(key=lambda d: d["serial"])

    output = {
        "schema_version": 1,
        "collector": "hardware_temperature",
        "observed_at": source.get("observed_at"),
        "host": SITE_NAME,
        "host_key_verified": True,
        "device_count": len(devices),
        "devices": devices,
    }

    print(json.dumps(output, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
