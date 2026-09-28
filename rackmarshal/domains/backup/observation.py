#!/usr/bin/env python3
import json
import sqlite3
import sys
from pathlib import Path

from rackmarshal.core.config import state_db


DB_FILE = state_db()

EXPECTED_COLLECTOR = 'backup_domain'

EXPECTED_SOURCE = (
    'Proxmox VE API + '
    'Proxmox Backup Server API'
)

EXPECTED_SCHEMA_VERSION = 1


class ValidationError(Exception):
    pass


def require(
    condition,
    message,
):
    if not condition:
        raise ValidationError(
            message
        )


def validate(data):
    require(
        isinstance(data, dict),
        'top-level JSON must be an object',
    )

    required = {
        'schema_version',
        'collector',
        'observed_at',
        'source',
        'tls_verified',
        'resource_count',
        'datastore',
        'backup_jobs',
        'recent_vzdump_tasks',
        'snapshot_count',
        'resources',
    }

    missing = required - data.keys()

    require(
        not missing,
        (
            'missing required fields: '
            + str(sorted(missing))
        ),
    )

    require(
        data['schema_version']
        == EXPECTED_SCHEMA_VERSION,
        'unsupported schema_version',
    )

    require(
        data['collector']
        == EXPECTED_COLLECTOR,
        'unexpected collector',
    )

    require(
        data['source']
        == EXPECTED_SOURCE,
        'unexpected source',
    )

    require(
        data['tls_verified'] is True,
        (
            'refusing observation because '
            'tls_verified is not true'
        ),
    )

    require(
        isinstance(
            data['observed_at'],
            str,
        )
        and data['observed_at'],
        'observed_at must be non-empty',
    )

    require(
        isinstance(
            data['datastore'],
            str,
        )
        and data['datastore'],
        'datastore must be non-empty',
    )

    require(
        isinstance(
            data['backup_jobs'],
            list,
        ),
        'backup_jobs must be an array',
    )

    require(
        isinstance(
            data['recent_vzdump_tasks'],
            list,
        ),
        (
            'recent_vzdump_tasks '
            'must be an array'
        ),
    )

    require(
        isinstance(
            data['snapshot_count'],
            int,
        )
        and not isinstance(
            data['snapshot_count'],
            bool,
        )
        and data['snapshot_count'] >= 0,
        (
            'snapshot_count must be '
            'a non-negative integer'
        ),
    )

    require(
        isinstance(
            data['resources'],
            list,
        ),
        'resources must be an array',
    )

    require(
        isinstance(
            data['resource_count'],
            int,
        )
        and not isinstance(
            data['resource_count'],
            bool,
        )
        and data['resource_count'] >= 0,
        (
            'resource_count must be '
            'a non-negative integer'
        ),
    )

    require(
        data['resource_count']
        == len(data['resources']),
        (
            'resource_count does not '
            'match resources length'
        ),
    )

    seen_vmids = set()

    for index, resource in enumerate(
        data['resources']
    ):
        require(
            isinstance(
                resource,
                dict,
            ),
            (
                f'resource {index} '
                'must be an object'
            ),
        )

        vmid = resource.get(
            'vmid'
        )

        require(
            isinstance(vmid, int)
            and not isinstance(
                vmid,
                bool,
            )
            and vmid > 0,
            (
                f'resource {index} '
                'has invalid vmid'
            ),
        )

        require(
            vmid not in seen_vmids,
            (
                'duplicate protected VMID: '
                f'{vmid}'
            ),
        )

        seen_vmids.add(
            vmid
        )

        require(
            resource.get(
                'policy_included'
            ) is True,
            (
                f'VMID {vmid} is not '
                'marked policy_included'
            ),
        )

        require(
            isinstance(
                resource.get(
                    'snapshot_present'
                ),
                bool,
            ),
            (
                f'VMID {vmid} has invalid '
                'snapshot_present'
            ),
        )

        snapshot = resource.get(
            'latest_snapshot'
        )

        if resource[
            'snapshot_present'
        ]:
            require(
                isinstance(
                    snapshot,
                    dict,
                ),
                (
                    f'VMID {vmid} claims '
                    'snapshot_present but '
                    'latest_snapshot is invalid'
                ),
            )

        else:
            require(
                snapshot is None,
                (
                    f'VMID {vmid} has '
                    'snapshot_present=false '
                    'but latest_snapshot exists'
                ),
            )

    return data


def main():
    try:
        payload = json.load(
            sys.stdin
        )

        data = validate(
            payload
        )

    except json.JSONDecodeError as exc:
        print(
            json.dumps(
                {
                    'schema_version': 1,
                    'writer':
                        'backup_observation',
                    'error':
                        (
                            'invalid input JSON: '
                            + str(exc)
                        ),
                },
                separators=(',', ':'),
            ),
            file=sys.stderr,
        )

        return 2

    except ValidationError as exc:
        print(
            json.dumps(
                {
                    'schema_version': 1,
                    'writer':
                        'backup_observation',
                    'error': str(exc),
                },
                separators=(',', ':'),
            ),
            file=sys.stderr,
        )

        return 2

    payload_json = json.dumps(
        data,
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True,
    )

    try:
        connection = sqlite3.connect(
            DB_FILE,
            timeout=10,
        )

        connection.execute(
            'PRAGMA foreign_keys = ON'
        )

        connection.execute(
            'BEGIN IMMEDIATE'
        )

        cursor = connection.execute(
            '''
            INSERT INTO observations (
                collector,
                observed_at,
                source,
                schema_version,
                tls_verified,
                resource_count,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                data['collector'],
                data['observed_at'],
                data['source'],
                data['schema_version'],
                1,
                data['resource_count'],
                payload_json,
            ),
        )

        observation_id = (
            cursor.lastrowid
        )

        connection.commit()

    except sqlite3.Error as exc:
        connection.rollback()

        print(
            json.dumps(
                {
                    'schema_version': 1,
                    'writer':
                        'backup_observation',
                    'error':
                        (
                            'database write failed: '
                            + str(exc)
                        ),
                },
                separators=(',', ':'),
            ),
            file=sys.stderr,
        )

        return 3

    finally:
        connection.close()

    print(
        json.dumps(
            {
                'schema_version': 1,
                'writer':
                    'backup_observation',
                'observation_id':
                    observation_id,
                'observed_at':
                    data['observed_at'],
                'resource_count':
                    data['resource_count'],
                'status': 'recorded',
            },
            indent=2,
        )
    )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
