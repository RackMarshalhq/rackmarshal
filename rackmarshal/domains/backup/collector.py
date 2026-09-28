#!/usr/bin/env python3
import os
import json
import subprocess
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from rackmarshal.core.config import (
    load_config,
    pbs_api_env,
    pbs_ca_file,
    pve_api_env,
    pve_ca_file,
    require,
)


CONFIG = load_config()

# Phase 2 Step 10: PVE/PBS credential + CA paths from config helpers
# (defaults = today's layout).
PVE_CONFIG_FILE = pve_api_env(CONFIG)
PBS_CONFIG_FILE = pbs_api_env(CONFIG)
PVE_CA_FILE = pve_ca_file(CONFIG)
PBS_CA_FILE = pbs_ca_file(CONFIG)

PVE_NODE = require(
    CONFIG,
    "PVE_NODE",
)


class CollectionError(Exception):
    pass



# --- STEP3_PBS_STORE_PROBE begin ---
def _backup_conf(key: str, default: str = "") -> str:
    if os.environ.get(key):
        return os.environ[key]
    conf = Path("/etc/rackmarshal/rackmarshal.conf")
    if conf.is_file():
        for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return default


def backup_ssh_configured() -> bool:
    return bool(
        _backup_conf("BACKUP_SSH_HOST")
        and _backup_conf("BACKUP_SSH_USER")
        and _backup_conf("BACKUP_SSH_KEY")
    )


def fetch_pbs_store_probe() -> dict:
    """SSH configured ForceCommand observer. Soft-fail with {_error}."""
    if not backup_ssh_configured():
        return {"_error": "backup_ssh_not_configured"}
    host = _backup_conf("BACKUP_SSH_HOST")
    user = _backup_conf("BACKUP_SSH_USER")
    key = _backup_conf("BACKUP_SSH_KEY")
    kh = (
        _backup_conf("BACKUP_KNOWN_HOSTS")
        or "/etc/rackmarshal/ssh/known_hosts"
    )
    try:
        proc = subprocess.run(
            [
                "/usr/bin/ssh",
                "-i", key,
                "-o", "BatchMode=yes",
                "-o", f"UserKnownHostsFile={kh}",
                "-o", "StrictHostKeyChecking=yes",
                "-o", "ConnectTimeout=10",
                f"{user}@{host}",
                "ignored",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"ssh_exc:{exc}"}
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        return {"_error": f"ssh_exit={proc.returncode}:{err}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"_error": f"bad_json:{exc}"}
# --- STEP3_PBS_STORE_PROBE end ---


def load_env(path, required):
    config = {}

    with path.open(
        'r',
        encoding='utf-8',
    ) as handle:
        for raw_line in handle:
            line = raw_line.strip()

            if (
                not line
                or line.startswith('#')
                or '=' not in line
            ):
                continue

            key, value = line.split('=', 1)

            key = key.strip()
            value = value.strip()

            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in ('"', "'")
            ):
                value = value[1:-1]

            config[key] = value

    missing = sorted(
        key
        for key in required
        if not config.get(key)
    )

    if missing:
        raise CollectionError(
            f'{path}: missing required configuration: '
            + ', '.join(missing)
        )

    return config


def api_get(
    base_url,
    endpoint,
    headers,
    cafile,
    label,
):
    url = base_url.rstrip('/') + endpoint

    request = urllib.request.Request(
        url,
        headers=headers,
        method='GET',
    )

    context = ssl.create_default_context(
        cafile=cafile
    )

    try:
        with urllib.request.urlopen(
            request,
            context=context,
            timeout=20,
        ) as response:
            payload = json.load(response)

    except urllib.error.HTTPError as exc:
        raise CollectionError(
            f'{label} HTTP error {exc.code} '
            f'for {endpoint}'
        ) from exc

    except urllib.error.URLError as exc:
        raise CollectionError(
            f'{label} connection error for '
            f'{endpoint}: {exc.reason}'
        ) from exc

    if not isinstance(payload, dict):
        raise CollectionError(
            f'{label} returned non-object JSON'
        )

    if 'data' not in payload:
        raise CollectionError(
            f'{label} response does not contain data'
        )

    return payload['data']


def pve_get(config, endpoint):
    headers = {
        'Authorization':
            'PVEAPIToken='
            + config['PVE_TOKEN_ID']
            + '='
            + config['PVE_TOKEN_SECRET'],
        'Accept': 'application/json',
        'User-Agent': 'RackMarshal/1.0',
    }

    return api_get(
        config['PVE_API_URL'],
        endpoint,
        headers,
        PVE_CA_FILE,
        'PVE API',
    )


def pbs_get(config, endpoint):
    headers = {
        'Authorization':
            'PBSAPIToken '
            + config['PBS_TOKEN_ID']
            + ':'
            + config['PBS_TOKEN_SECRET'],
        'Accept': 'application/json',
        'User-Agent': 'RackMarshal/1.0',
    }

    return api_get(
        config['PBS_API_URL'],
        endpoint,
        headers,
        PBS_CA_FILE,
        'PBS API',
    )


def parse_vmids(value):
    if value is None:
        return []

    output = []

    for item in str(value).split(','):
        item = item.strip()

        if not item:
            continue

        try:
            vmid = int(item)
        except ValueError as exc:
            raise CollectionError(
                f'invalid VMID in backup policy: '
                f'{item!r}'
            ) from exc

        output.append(vmid)

    return sorted(set(output))


def normalize_policy(job):
    return {
        'id': job.get('id'),
        'enabled': bool(
            int(job.get('enabled', 1))
        ),
        'node': job.get('node'),
        'mode': job.get('mode'),
        'storage': job.get('storage'),
        'schedule': job.get('schedule'),
        'vmids': parse_vmids(
            job.get('vmid')
        ),
        'notes_template':
            job.get('notes-template'),
        'prune': {
            'keep_daily':
                job.get('prune-backups', {})
                .get('keep-daily')
                if isinstance(
                    job.get('prune-backups'),
                    dict,
                )
                else None,
            'keep_last':
                job.get('prune-backups', {})
                .get('keep-last')
                if isinstance(
                    job.get('prune-backups'),
                    dict,
                )
                else None,
            'keep_weekly':
                job.get('prune-backups', {})
                .get('keep-weekly')
                if isinstance(
                    job.get('prune-backups'),
                    dict,
                )
                else None,
            'keep_monthly':
                job.get('prune-backups', {})
                .get('keep-monthly')
                if isinstance(
                    job.get('prune-backups'),
                    dict,
                )
                else None,
            'keep_yearly':
                job.get('prune-backups', {})
                .get('keep-yearly')
                if isinstance(
                    job.get('prune-backups'),
                    dict,
                )
                else None,
        },
    }


def normalize_task(task):
    fields = (
        'upid',
        'node',
        'pid',
        'pstart',
        'starttime',
        'endtime',
        'type',
        'id',
        'user',
        'status',
    )

    output = {}

    for field in fields:
        value = task.get(field)

        if value is not None:
            output[field] = value

    return output


def latest_snapshots(rows):
    latest = {}

    for row in rows:
        backup_type = row.get('backup-type')
        backup_id = row.get('backup-id')

        if backup_type not in ('vm', 'ct'):
            continue

        if backup_id is None:
            continue

        try:
            vmid = int(str(backup_id))
        except ValueError:
            continue

        key = (
            backup_type,
            vmid,
        )

        backup_time = row.get(
            'backup-time',
            0,
        )

        existing = latest.get(key)

        if (
            existing is None
            or backup_time
            > existing.get(
                'backup-time',
                0,
            )
        ):
            latest[key] = row

    return latest


def snapshot_summary(row):
    if row is None:
        return None

    verification = (
        row.get('verification')
        if isinstance(
            row.get('verification'),
            dict,
        )
        else {}
    )

    return {
        'backup_type':
            row.get('backup-type'),
        'backup_id':
            row.get('backup-id'),
        'backup_time':
            row.get('backup-time'),
        'verification_state':
            verification.get('state'),
    }


def guest_inventory(resources):
    output = {}

    for resource in resources:
        resource_type = resource.get('type')

        if resource_type not in (
            'qemu',
            'lxc',
        ):
            continue

        vmid = resource.get('vmid')

        if not isinstance(vmid, int):
            continue

        output[vmid] = {
            'guest_type':
                'vm'
                if resource_type == 'qemu'
                else 'ct',
            'name': resource.get('name'),
            'node': resource.get('node'),
            'status': resource.get('status'),
        }

    return output


def main():
    try:
        pve = load_env(
            PVE_CONFIG_FILE,
            {
                'PVE_API_URL',
                'PVE_TOKEN_ID',
                'PVE_TOKEN_SECRET',
            },
        )

        pbs = load_env(
            PBS_CONFIG_FILE,
            {
                'PBS_API_URL',
                'PBS_TOKEN_ID',
                'PBS_TOKEN_SECRET',
                'PBS_DATASTORE',
            },
        )

        raw_policy = pve_get(
            pve,
            '/cluster/backup',
        )

        if not isinstance(
            raw_policy,
            list,
        ):
            raise CollectionError(
                'PVE backup policy response '
                'must be an array'
            )

        policy = [
            normalize_policy(job)
            for job in raw_policy
        ]

        relevant_jobs = [
            job
            for job in policy
            if (
                job['enabled']
                and job['storage'] == 'pbs'
            )
        ]

        protected_vmids = sorted(
            {
                vmid
                for job in relevant_jobs
                for vmid in job['vmids']
            }
        )

        raw_resources = pve_get(
            pve,
            '/cluster/resources',
        )

        inventory = guest_inventory(
            raw_resources
        )

        raw_tasks = pve_get(
            pve,
            (
                f'/nodes/{PVE_NODE}/tasks'
                '?typefilter=vzdump&limit=100'
            ),
        )

        if not isinstance(
            raw_tasks,
            list,
        ):
            raise CollectionError(
                'PVE task response must be an array'
            )

        recent_vzdump_tasks = [
            normalize_task(task)
            for task in raw_tasks
        ]

        store = pbs['PBS_DATASTORE']

        raw_snapshots = pbs_get(
            pbs,
            (
                '/api2/json/admin/datastore/'
                + store
                + '/snapshots'
            ),
        )

        if not isinstance(
            raw_snapshots,
            list,
        ):
            raise CollectionError(
                'PBS snapshot response '
                'must be an array'
            )

        latest = latest_snapshots(
            raw_snapshots
        )

        targets = []

        for vmid in protected_vmids:
            guest = inventory.get(
                vmid,
                {},
            )

            guest_type = guest.get(
                'guest_type'
            )

            row = None

            if guest_type:
                row = latest.get(
                    (
                        guest_type,
                        vmid,
                    )
                )

            if row is None:
                for candidate_type in (
                    'vm',
                    'ct',
                ):
                    candidate = latest.get(
                        (
                            candidate_type,
                            vmid,
                        )
                    )

                    if candidate is not None:
                        row = candidate
                        guest_type = candidate_type
                        break

            snapshot = snapshot_summary(
                row
            )

            targets.append(
                {
                    'vmid': vmid,
                    'name':
                        guest.get('name'),
                    'guest_type':
                        guest_type,
                    'node':
                        guest.get('node'),
                    'guest_status':
                        guest.get('status'),
                    'policy_included': True,
                    'snapshot_present':
                        snapshot is not None,
                    'latest_snapshot':
                        snapshot,
                }
            )

        observation = {
            'schema_version': 1,
            'collector':
                'backup_domain',
            'observed_at':
                datetime.now(
                    timezone.utc
                )
                .isoformat()
                .replace(
                    '+00:00',
                    'Z',
                ),
            'source':
                (
                    'Proxmox VE API + '
                    'Proxmox Backup Server API'
                ),
            'tls_verified': True,
            'resource_count':
                len(targets),
            'datastore': store,
            'backup_jobs': policy,
            'recent_vzdump_tasks':
                recent_vzdump_tasks,
            'snapshot_count':
                len(raw_snapshots),
            'resources':
                targets,
        }


        # --- STEP3_PBS_STORE_PROBE attach ---
        if backup_ssh_configured():
            try:
                observation["pbs_store_probe"] = fetch_pbs_store_probe()
            except Exception as _exc:  # noqa: BLE001
                observation["pbs_store_probe"] = {"_error": f"attach_exc:{_exc}"}
        # --- STEP3_PBS_STORE_PROBE attach end ---

        print(
            json.dumps(
                observation,
                indent=2,
                sort_keys=False,
            )
        )

        return 0

    except (
        OSError,
        CollectionError,
    ) as exc:
        print(
            json.dumps(
                {
                    'schema_version': 1,
                    'collector':
                        'backup_domain',
                    'error': str(exc),
                },
                separators=(',', ':'),
            )
        )

        return 1


if __name__ == '__main__':
    raise SystemExit(main())
