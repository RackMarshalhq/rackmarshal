-- ZFS ledger: observations, pool/vdev baselines, events, incidents, processing
-- fresh-host drill F2 2026-09-17; CREATE IF NOT EXISTS from CT 110 live schema

-- table: zfs_observations
CREATE TABLE IF NOT EXISTS zfs_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    observed_at TEXT NOT NULL,

    source TEXT NOT NULL,

    schema_version INTEGER NOT NULL
        CHECK (schema_version >= 1),

    host_key_verified INTEGER NOT NULL
        CHECK (host_key_verified IN (0,1)),

    pool_count INTEGER NOT NULL
        CHECK (pool_count >= 0),

    payload_json TEXT NOT NULL,

    recorded_at TEXT NOT NULL
        DEFAULT (
            strftime(
                '%Y-%m-%dT%H:%M:%fZ',
                'now'
            )
        )
);
CREATE INDEX IF NOT EXISTS idx_zfs_observations_observed_at
    ON zfs_observations(observed_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_zfs_observations_observed_at_unique
    ON zfs_observations(observed_at);

-- table: zfs_pool_baseline
CREATE TABLE IF NOT EXISTS zfs_pool_baseline (
    pool_name TEXT PRIMARY KEY,

    pool_guid TEXT NOT NULL UNIQUE,

    baseline_state TEXT NOT NULL
        CHECK (
            baseline_state IN (
                'VERIFIED',
                'EXPECTED',
                'KNOWN-ISSUE',
                'FAILED',
                'DECOMMISSIONED'
            )
        ),

    expected_state TEXT NOT NULL,

    expected_error_count INTEGER NOT NULL
        CHECK (expected_error_count >= 0),

    source_observation_id INTEGER NOT NULL,

    note TEXT,

    created_at TEXT NOT NULL
        DEFAULT (
            strftime(
                '%Y-%m-%dT%H:%M:%fZ',
                'now'
            )
        ),

    FOREIGN KEY (source_observation_id)
        REFERENCES zfs_observations(id)
        ON DELETE RESTRICT
);

-- table: zfs_vdev_baseline
CREATE TABLE IF NOT EXISTS zfs_vdev_baseline (
    pool_name TEXT NOT NULL,

    vdev_name TEXT NOT NULL,

    vdev_type TEXT NOT NULL,

    baseline_state TEXT NOT NULL
        CHECK (
            baseline_state IN (
                'VERIFIED',
                'EXPECTED',
                'KNOWN-ISSUE',
                'FAILED',
                'DECOMMISSIONED'
            )
        ),

    expected_state TEXT NOT NULL,

    expected_read_errors INTEGER NOT NULL
        CHECK (expected_read_errors >= 0),

    expected_write_errors INTEGER NOT NULL
        CHECK (expected_write_errors >= 0),

    expected_checksum_errors INTEGER NOT NULL
        CHECK (expected_checksum_errors >= 0),

    expected_slow_ios INTEGER
        CHECK (
            expected_slow_ios IS NULL
            OR expected_slow_ios >= 0
        ),

    path TEXT,

    phys_path TEXT,

    source_observation_id INTEGER NOT NULL,

    note TEXT,

    created_at TEXT NOT NULL
        DEFAULT (
            strftime(
                '%Y-%m-%dT%H:%M:%fZ',
                'now'
            )
        ),

    PRIMARY KEY (
        pool_name,
        vdev_name
    ),

    FOREIGN KEY (pool_name)
        REFERENCES zfs_pool_baseline(pool_name)
        ON DELETE CASCADE,

    FOREIGN KEY (source_observation_id)
        REFERENCES zfs_observations(id)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_zfs_vdev_baseline_pool
    ON zfs_vdev_baseline(pool_name);

-- table: zfs_events
CREATE TABLE IF NOT EXISTS zfs_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    observation_id INTEGER NOT NULL,

    resource_type TEXT NOT NULL
        CHECK (
            resource_type IN (
                'zfs_pool',
                'zfs_vdev'
            )
        ),

    resource_key TEXT NOT NULL,

    pool_name TEXT NOT NULL,

    vdev_name TEXT,

    outcome TEXT NOT NULL
        CHECK (
            outcome IN (
                'STATUS-CHANGED',
                'COUNTER-CHANGED',
                'MISSING',
                'NEW'
            )
        ),

    baseline_state TEXT
        CHECK (
            baseline_state IS NULL
            OR baseline_state IN (
                'VERIFIED',
                'EXPECTED',
                'KNOWN-ISSUE',
                'FAILED',
                'DECOMMISSIONED'
            )
        ),

    changes_json TEXT NOT NULL,

    observed_at TEXT NOT NULL,

    recorded_at TEXT NOT NULL
        DEFAULT (
            strftime(
                '%Y-%m-%dT%H:%M:%fZ',
                'now'
            )
        ),

    FOREIGN KEY (
        observation_id
    )
    REFERENCES zfs_observations(id)
    ON DELETE RESTRICT,

    UNIQUE (
        observation_id,
        resource_type,
        resource_key,
        outcome
    )
);
CREATE INDEX IF NOT EXISTS idx_zfs_events_observation
ON zfs_events(
    observation_id
);
CREATE INDEX IF NOT EXISTS idx_zfs_events_resource
ON zfs_events(
    resource_type,
    resource_key,
    observed_at
);

-- table: zfs_incidents
CREATE TABLE IF NOT EXISTS zfs_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    resource_type TEXT NOT NULL
        CHECK (
            resource_type IN (
                'zfs_pool',
                'zfs_vdev'
            )
        ),

    resource_key TEXT NOT NULL,

    pool_name TEXT NOT NULL,

    vdev_name TEXT,

    incident_type TEXT NOT NULL
        CHECK (
            incident_type IN (
                'STATUS-CHANGED',
                'MISSING',
                'NEW'
            )
        ),

    incident_state TEXT NOT NULL
        CHECK (
            incident_state IN (
                'OPEN',
                'RECOVERED'
            )
        ),

    baseline_state TEXT
        CHECK (
            baseline_state IS NULL
            OR baseline_state IN (
                'VERIFIED',
                'EXPECTED',
                'KNOWN-ISSUE',
                'FAILED',
                'DECOMMISSIONED'
            )
        ),

    opened_event_id INTEGER NOT NULL,

    last_event_id INTEGER NOT NULL,

    opened_observation_id INTEGER NOT NULL,

    last_abnormal_observation_id INTEGER NOT NULL,

    recovered_observation_id INTEGER,

    opened_at TEXT NOT NULL,

    last_abnormal_at TEXT NOT NULL,

    recovered_at TEXT,

    occurrence_count INTEGER NOT NULL DEFAULT 1
        CHECK (occurrence_count >= 1),

    opening_changes_json TEXT NOT NULL,

    latest_changes_json TEXT NOT NULL,

    note TEXT,

    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),

    updated_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),

    FOREIGN KEY (opened_event_id)
        REFERENCES zfs_events(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (last_event_id)
        REFERENCES zfs_events(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (opened_observation_id)
        REFERENCES zfs_observations(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (last_abnormal_observation_id)
        REFERENCES zfs_observations(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (recovered_observation_id)
        REFERENCES zfs_observations(id)
        ON DELETE RESTRICT,

    CHECK (
        (
            incident_state='OPEN'
            AND recovered_observation_id IS NULL
            AND recovered_at IS NULL
        )
        OR
        (
            incident_state='RECOVERED'
            AND recovered_observation_id IS NOT NULL
            AND recovered_at IS NOT NULL
        )
    ),

    CHECK (
        (
            resource_type='zfs_pool'
            AND vdev_name IS NULL
        )
        OR
        resource_type='zfs_vdev'
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_zfs_incidents_one_open
ON zfs_incidents (
    resource_type,
    resource_key,
    incident_type
)
WHERE incident_state='OPEN';
CREATE INDEX IF NOT EXISTS idx_zfs_incidents_state
ON zfs_incidents(
    incident_state,
    updated_at
);
CREATE INDEX IF NOT EXISTS idx_zfs_incidents_resource
ON zfs_incidents(
    resource_type,
    resource_key,
    opened_at
);
CREATE INDEX IF NOT EXISTS idx_zfs_incidents_opened_event
ON zfs_incidents(opened_event_id);
CREATE INDEX IF NOT EXISTS idx_zfs_incidents_last_event
ON zfs_incidents(last_event_id);
CREATE INDEX IF NOT EXISTS idx_zfs_incidents_opened_observation
ON zfs_incidents(opened_observation_id);
CREATE INDEX IF NOT EXISTS idx_zfs_incidents_last_abnormal_observation
ON zfs_incidents(last_abnormal_observation_id);
CREATE INDEX IF NOT EXISTS idx_zfs_incidents_recovered_observation
ON zfs_incidents(recovered_observation_id);

-- table: zfs_incident_processing
CREATE TABLE IF NOT EXISTS zfs_incident_processing (
    observation_id INTEGER PRIMARY KEY,

    differences_detected INTEGER NOT NULL DEFAULT 0
        CHECK (differences_detected >= 0),

    incidents_opened INTEGER NOT NULL DEFAULT 0
        CHECK (incidents_opened >= 0),

    incidents_ongoing INTEGER NOT NULL DEFAULT 0
        CHECK (incidents_ongoing >= 0),

    incidents_recovered INTEGER NOT NULL DEFAULT 0
        CHECK (incidents_recovered >= 0),

    processed_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),

    note TEXT,

    FOREIGN KEY (observation_id)
        REFERENCES zfs_observations(id)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_zfs_incident_processing_processed
ON zfs_incident_processing(processed_at);

