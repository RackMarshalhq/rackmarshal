#!/usr/bin/env python3

import collections
import datetime
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

from rackmarshal.core.config import ha_credential_file

# Phase 2 Step 9: HA credential path from config helper (default = today's layout).
CREDENTIAL = str(ha_credential_file())


class CollectorError(Exception):
    pass


def utc_now():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def load_credentials():
    command = r'''
set -a
. "$1"
printf '%s\0%s' "$HA_URL" "$HA_TOKEN"
'''

    result = subprocess.run(
        ["bash", "-c", command, "_", CREDENTIAL],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        raise CollectorError(
            "unable to load Home Assistant credentials"
        )

    parts = result.stdout.split(b"\0", 1)

    if len(parts) != 2:
        raise CollectorError(
            "invalid Home Assistant credential output"
        )

    url = parts[0].decode().strip().rstrip("/")
    token = parts[1].decode().strip()

    if not url or not token:
        raise CollectorError(
            "Home Assistant URL/token missing"
        )

    return url, token


def api_get(base_url, token, path):
    request = urllib.request.Request(
        base_url + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=15,
        ) as response:
            body = response.read()
            status = response.status

    except urllib.error.HTTPError as exc:
        raise CollectorError(
            f"Home Assistant HTTP {exc.code}"
        ) from exc

    except Exception as exc:
        raise CollectorError(
            "Home Assistant request failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if status != 200:
        raise CollectorError(
            f"Home Assistant returned HTTP {status}"
        )

    try:
        return json.loads(body)

    except json.JSONDecodeError as exc:
        raise CollectorError(
            "Home Assistant returned invalid JSON"
        ) from exc


def main():
    observed_at = utc_now()
    base_url, token = load_credentials()

    api_root = api_get(
        base_url,
        token,
        "/api/",
    )

    config = api_get(
        base_url,
        token,
        "/api/config",
    )

    states = api_get(
        base_url,
        token,
        "/api/states",
    )

    if not isinstance(states, list):
        raise CollectorError(
            "/api/states did not return a list"
        )

    domain_counts = collections.Counter()
    state_counts = collections.Counter()

    for row in states:
        entity_id = str(
            row.get("entity_id", "")
        )

        if "." in entity_id:
            domain = entity_id.split(".", 1)[0]
        else:
            domain = "unknown"

        domain_counts[domain] += 1

        state_counts[
            str(row.get("state"))
        ] += 1

    api_message = api_root.get("message")
    core_state = config.get("state")

    resources = [
        {
            "resource_type": "ha_api",
            "resource_key": "home_assistant_api",
            "display_name": "Home Assistant API",
            "status": (
                "OK"
                if api_message == "API running."
                else "ABNORMAL"
            ),
            "expected_status": "OK",
            "actual_value": api_message,
        },
        {
            "resource_type": "ha_core",
            "resource_key": "home_assistant_core",
            "display_name": "Home Assistant Core",
            "status": (
                "RUNNING"
                if core_state == "RUNNING"
                else str(core_state)
            ),
            "expected_status": "RUNNING",
            "actual_value": core_state,
        },
    ]

    result = {
        "schema_version": 1,
        "collector": "home_assistant",
        "observed_at": observed_at,
        "source": "Home Assistant REST API",
        "tls_verified": (
            1
            if base_url.lower().startswith("https://")
            else 0
        ),
        "resource_count": len(resources),
        "resources": resources,
        "metadata": {
            "version": config.get("version"),
            "time_zone": config.get("time_zone"),
            "country": config.get("country"),
            "currency": config.get("currency"),
            "language": config.get("language"),
            "component_count": len(
                config.get("components", [])
            ),
            "entity_count": len(states),
            "domain_count": len(domain_counts),
            "unavailable_count":
                state_counts.get("unavailable", 0),
            "unknown_count":
                state_counts.get("unknown", 0),
            "domain_counts": dict(
                sorted(domain_counts.items())
            ),
        },
    }

    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except CollectorError as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
