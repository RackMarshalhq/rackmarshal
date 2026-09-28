-- BACKUP ledger: events, guest/job baselines, incidents, processing
-- fresh-host drill F2 2026-09-17; CREATE IF NOT EXISTS from CT 110 live schema

-- table: backup_guest_baseline
CREATE TABLE IF NOT EXISTS backup_guest_baseline (
    vmid INTEGER PRIMARY KEY
        CHECK (vmid > 0),

    display_name TEXT NOT NULL,

    guest_type TEXT NOT NULL
        CHECK (
            guest_type IN (
                'vm',
                'ct'
            )
        ),

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

    expected_job_id TEXT NOT NULL,

    expected_policy_included INTEGER NOT NULL
        CHECK (
            expected_policy_included IN (0,1)
        ),

    expected_snapshot_present INTEGER NOT NULL
        CHECK (
            expected_snapshot_present IN (0,1)
        ),

    expected_verification_state TEXT NOT NULL,

    max_snapshot_age_hours REAL NOT NULL
        CHECK (max_snapshot_age_hours > 0),

    source_observation_id INTEGER NOT NULL,

    note TEXT,

    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),

    FOREIGN KEY (expected_job_id)
        REFERENCES backup_job_baseline(job_id)
        ON DELETE RESTRICT,

    FOREIGN KEY (source_observation_id)
        REFERENCES observations(id)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_backup_guest_baseline_state
ON backup_guest_baseline(
    baseline_state
);

-- table: backup_job_baseline
CREATE TABLE IF NOT EXISTS backup_job_baseline (
    job_id TEXT PRIMARY KEY,

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

    expected_enabled INTEGER NOT NULL
        CHECK (expected_enabled IN (0,1)),

    expected_node TEXT NOT NULL,

    expected_mode TEXT NOT NULL,

    expected_storage TEXT NOT NULL,

    expected_schedule TEXT NOT NULL,

    expected_notes_template TEXT,

    expected_keep_daily TEXT,
    expected_keep_last TEXT,
    expected_keep_weekly TEXT,
    expected_keep_monthly TEXT,
    expected_keep_yearly TEXT,

    source_observation_id INTEGER NOT NULL,

    note TEXT,

    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),

    FOREIGN KEY (source_observation_id)
        REFERENCES observations(id)
        ON DELETE RESTRICT
);

-- table: backup_events
CREATE TABLE IF NOT EXISTS backup_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    observation_id INTEGER NOT NULL,

    resource_type TEXT NOT NULL
        CHECK (
            resource_type IN (
                'backup_job',
                'backup_guest',
                'backup_scheduled_run'
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
CREATE INDEX IF NOT EXISTS idx_backup_events_observation
ON backup_events(
    observation_id
);
CREATE INDEX IF NOT EXISTS idx_backup_events_resource
ON backup_events(
    resource_type,
    resource_key,
    observed_at
);

-- table: backup_incidents
CREATE TABLE IF NOT EXISTS backup_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    resource_type TEXT NOT NULL
        CHECK (
            resource_type IN (
                'backup_job',
                'backup_guest',
                'backup_scheduled_run'
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
        REFERENCES backup_events(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (last_event_id)
        REFERENCES backup_events(id)
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
            incident_state = 'OPEN'
            AND recovered_observation_id IS NULL
            AND recovered_at IS NULL
        )
        OR
        (
            incident_state = 'RECOVERED'
            AND recovered_observation_id IS NOT NULL
            AND recovered_at IS NOT NULL
        )
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_backup_incidents_one_open
ON backup_incidents(
    resource_type,
    resource_key,
    incident_type
)
WHERE incident_state = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_backup_incidents_state
ON backup_incidents(
    incident_state,
    updated_at
);
CREATE INDEX IF NOT EXISTS idx_backup_incidents_resource
ON backup_incidents(
    resource_type,
    resource_key,
    opened_at
);

-- table: backup_incident_processing
CREATE TABLE IF NOT EXISTS backup_incident_processing (
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
CREATE INDEX IF NOT EXISTS idx_backup_incident_processing_processed
ON backup_incident_processing(
    processed_at
);

