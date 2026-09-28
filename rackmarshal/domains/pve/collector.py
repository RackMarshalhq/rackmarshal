#!/usr/bin/env python3

import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from rackmarshal.core.config import pve_api_env, pve_ca_file

# Phase 2 Step 8: credential/CA paths from config helpers (defaults = today's layout).
CONFIG_FILE = pve_api_env()
CA_FILE = pve_ca_file()


def load_config(path):
    config = {}

    with path.open('r', encoding='utf-8') as handle:
        for raw_line in handle:
            line = raw_line.strip()

            if not line or line.startswith('#') or '=' not in line:
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

    required = {
        'PVE_API_URL',
        'PVE_TOKEN_ID',
        'PVE_TOKEN_SECRET',
    }

    missing = sorted(required - config.keys())

    if missing:
        raise RuntimeError(
            'Missing required configuration: '
            + ', '.join(missing)
        )

    return config


def api_get(config, endpoint):
    url = config['PVE_API_URL'].rstrip('/') + endpoint

    request = urllib.request.Request(
        url,
        headers={
            'Authorization':
                'PVEAPIToken='
                + config['PVE_TOKEN_ID']
                + '='
                + config['PVE_TOKEN_SECRET'],
            'Accept': 'application/json',
            'User-Agent': 'RackMarshal/1.0',
        },
        method='GET',
    )

    context = ssl.create_default_context(cafile=str(CA_FILE))

    try:
        with urllib.request.urlopen(
            request,
            context=context,
            timeout=10,
        ) as response:
            payload = json.load(response)

    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f'PVE API HTTP error {exc.code}'
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f'PVE API connection error: {exc.reason}'
        ) from exc

    if 'data' not in payload:
        raise RuntimeError(
            'PVE API response does not contain data'
        )

    return payload['data']


def normalized_resource(resource):
    output = {
        'type': resource.get('type'),
    }

    fields = (
        'vmid',
        'name',
        'node',
        'status',
        'uptime',
        'cpu',
        'mem',
        'maxmem',
        'disk',
        'maxdisk',
        'storage',
        'plugintype',
        'content',
    )

    for field in fields:
        if field in resource and resource[field] is not None:
            output[field] = resource[field]

    return output


def sort_key(resource):
    vmid = resource.get('vmid')

    if isinstance(vmid, int):
        vmid_key = vmid
    else:
        vmid_key = 999999999

    return (
        str(resource.get('type', '')),
        vmid_key,
        str(
            resource.get('name')
            or resource.get('storage')
            or resource.get('node')
            or ''
        ),
    )


def main():
    config = load_config(CONFIG_FILE)

    raw_resources = api_get(
        config,
        '/cluster/resources',
    )

    resources = [
        normalized_resource(resource)
        for resource in raw_resources
    ]

    resources.sort(key=sort_key)

    observation = {
        'schema_version': 1,
        'collector': 'pve_cluster_resources',
        'observed_at':
            datetime.now(timezone.utc)
            .isoformat()
            .replace('+00:00', 'Z'),
        'source': 'Proxmox VE API',
        'tls_verified': True,
        'resource_count': len(resources),
        'resources': resources,
    }

    print(
        json.dumps(
            observation,
            indent=2,
            sort_keys=False,
        )
    )


if __name__ == '__main__':
    main()
