#!/usr/bin/env python3

import json
import subprocess
import sys
from datetime import datetime, timezone

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
    "ZFS_SSH_HOST",
)

SSH_USER = require(
    CONFIG,
    "ZFS_SSH_USER",
)

SSH_KEY = require(
    CONFIG,
    "ZFS_SSH_KEY",
)

KNOWN_HOSTS = require(
    CONFIG,
    "ZFS_KNOWN_HOSTS",
)


def fail(message, rc=1):
    print(
        json.dumps(
            {
                "schema_version": 1,
                "collector": "zfs_status",
                "error": message,
            },
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )
    raise SystemExit(rc)


def run_zpool_status():
    command = [
        "/usr/bin/ssh",
        "-T",
        "-i",
        SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        f"{SSH_USER}@{SSH_HOST}",
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail("SSH request timed out")

    except OSError as exc:
        fail(f"Unable to execute SSH client: {exc}")

    if result.returncode != 0:
        stderr = result.stderr.strip()

        if stderr:
            fail(
                "SSH/ZFS collection failed: "
                + stderr.replace("\n", " ")
            )

        fail(
            "SSH/ZFS collection failed with exit code "
            + str(result.returncode)
        )

    try:
        return json.loads(result.stdout)

    except json.JSONDecodeError as exc:
        fail(
            "ZFS source returned invalid JSON: "
            + str(exc)
        )


def int_value(value, field_name, pool_name):
    try:
        return int(value)
    except (TypeError, ValueError):
        fail(
            f"Pool {pool_name} has invalid "
            f"{field_name}: {value!r}"
        )


def optional_int(value, field_name, context):
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        fail(
            f"{context} has invalid "
            f"{field_name}: {value!r}"
        )


def normalize_scan(scan, pool_name):
    if not isinstance(scan, dict):
        return None

    result = {}

    for field in (
        "function",
        "state",
    ):
        if field in scan:
            result[field] = scan[field]

    for field in (
        "errors",
        "start_time",
        "end_time",
        "examined",
        "issued",
        "skipped",
        "processed",
        "to_examine",
        "pass_exam",
        "pass_issued",
    ):
        if field in scan:
            result[field] = optional_int(
                scan[field],
                field,
                f"Pool {pool_name} scan",
            )

    return result


def normalize_vdev(name, vdev):
    if not isinstance(vdev, dict):
        return None

    context = f"Vdev {vdev.get('name', name)}"

    result = {
        "name": vdev.get("name", name),
        "type": vdev.get("vdev_type"),
        "state": vdev.get("state"),
        "read_errors": optional_int(
            vdev.get("read_errors"),
            "read_errors",
            context,
        ),
        "write_errors": optional_int(
            vdev.get("write_errors"),
            "write_errors",
            context,
        ),
        "checksum_errors": optional_int(
            vdev.get("checksum_errors"),
            "checksum_errors",
            context,
        ),
        "slow_ios": optional_int(
            vdev.get("slow_ios"),
            "slow_ios",
            context,
        ),
        "path": vdev.get("path"),
        "phys_path": vdev.get("phys_path"),
    }

    children = vdev.get("vdevs")

    if isinstance(children, dict):
        normalized_children = []

        for child_name in sorted(children):
            child = normalize_vdev(
                child_name,
                children[child_name],
            )

            if child is not None:
                normalized_children.append(child)

        result["children"] = normalized_children

    else:
        result["children"] = []

    return result


def main():
    source = run_zpool_status()

    pools = source.get("pools")

    if not isinstance(pools, dict):
        fail("ZFS JSON does not contain a pools object")

    normalized_pools = []

    for pool_name in sorted(pools):
        pool = pools[pool_name]

        if not isinstance(pool, dict):
            fail(f"Pool {pool_name} is not an object")

        state = pool.get("state")

        if not isinstance(state, str) or not state:
            fail(f"Pool {pool_name} has no valid state")

        root_vdevs = pool.get("vdevs")
        normalized_vdevs = []

        if isinstance(root_vdevs, dict):
            for vdev_name in sorted(root_vdevs):
                vdev = normalize_vdev(
                    vdev_name,
                    root_vdevs[vdev_name],
                )

                if vdev is not None:
                    normalized_vdevs.append(vdev)

        normalized_pools.append(
            {
                "name": pool_name,
                "pool_guid": pool.get("pool_guid"),
                "state": state,
                "error_count": int_value(
                    pool.get("error_count", 0),
                    "error_count",
                    pool_name,
                ),
                "scan": normalize_scan(
                    pool.get("scan_stats"),
                    pool_name,
                ),
                "vdevs": normalized_vdevs,
            }
        )

    output = {
        "schema_version": 1,
        "collector": "zfs_status",
        "observed_at": datetime.now(
            timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "source": (
            f"{SITE_NAME}:/usr/sbin/zpool status -j -p "
            "via forced-command SSH"
        ),
        "ssh_host": SSH_HOST,
        "host_key_verified": True,
        "pool_count": len(normalized_pools),
        "pools": normalized_pools,
    }

    print(
        json.dumps(
            output,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
