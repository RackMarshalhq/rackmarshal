-- HA ledger: events, baselines, incidents, processing
-- fresh-host drill F2 2026-09-17; CREATE IF NOT EXISTS from CT 110 live schema

-- table: ha_resource_baseline
CREATE TABLE IF NOT EXISTS ha_resource_baseline (
    resource_key TEXT PRIMARY KEY,

    resource_type TEXT NOT NULL,

    display_name TEXT NOT NULL,

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

    expected_status TEXT NOT NULL,

    source_observation_id INTEGER NOT NULL,

    note TEXT,

    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),

    FOREIGN KEY (source_observation_id)
        REFERENCES observations(id)
        ON DELETE RESTRICT
);

-- table: ha_events
CREATE TABLE IF NOT EXISTS ha_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    observation_id INTEGER NOT NULL,

    resource_type TEXT NOT NULL
        CHECK (
            resource_type IN (
                'ha_api',
                'ha_core'
            )
        ),

    resource_key TEXT NOT NULL,

    outcome TEXT NOT NULL
        CHECK (
            outcome IN (
                'STATUS-CHANGED',
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

    recorded_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),

    FOREIGN KEY (observation_id)
        REFERENCES observations(id)
        ON DELETE RESTRICT,

    UNIQUE (
        observation_id,
        resource_type,
        resource_key,
        outcome
    )
);

-- table: ha_incidents
CREATE TABLE IF NOT EXISTS ha_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    resource_type TEXT NOT NULL
        CHECK (
            resource_type IN (
                'ha_api',
                'ha_core'
            )
        ),

    resource_key TEXT NOT NULL,

    display_name TEXT NOT NULL,

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
        REFERENCES ha_events(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (last_event_id)
        REFERENCES ha_events(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (opened_observation_id)
        REFERENCES observations(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (last_abnormal_observation_id)
        REFERENCES observations(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (recovered_observation_id)
        REFERENCES observations(id)
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
    )
);

-- table: ha_incident_processing
CREATE TABLE IF NOT EXISTS ha_incident_processing (
    observation_id INTEGER PRIMARY KEY,

    processing_kind TEXT NOT NULL
        CHECK (
            processing_kind IN (
                'BOOTSTRAP',
                'PROCESSED'
            )
        ),

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
        REFERENCES observations(id)
        ON DELETE RESTRICT
);

