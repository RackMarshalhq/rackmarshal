-- RackMarshal 011_backup_resource_types
-- The backup domain records events and incidents for eight resource types,
-- but 004_backup_ledger limited resource_type to three of them. On a fresh
-- install the other five were rejected by the CHECK constraint (events.py
-- uses INSERT OR IGNORE, so the rows were silently dropped) and incident
-- processing then failed with "missing backup event". This migration
-- rebuilds both tables with the full list, preserving every row and id.
-- 004 itself is left unchanged so existing checksums stay valid.

DROP INDEX IF EXISTS idx_backup_events_observation;
DROP INDEX IF EXISTS idx_backup_events_resource;
DROP INDEX IF EXISTS idx_backup_incidents_one_open;
DROP INDEX IF EXISTS idx_backup_incidents_state;
DROP INDEX IF EXISTS idx_backup_incidents_resource;

ALTER TABLE backup_incidents RENAME TO backup_incidents_old;
ALTER TABLE backup_events RENAME TO backup_events_old;

-- table: backup_events
CREATE TABLE backup_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    observation_id INTEGER NOT NULL,

    resource_type TEXT NOT NULL
        CHECK (
            resource_type IN (
                'backup_job',
                'backup_guest',
                'backup_scheduled_run',
                'backup_timemachine',
                'backup_phone',
                'backup_messages',
                'backup_host_verify',
                'backup_rsync_filebackups'
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
CREATE INDEX idx_backup_events_observation
ON backup_events(
    observation_id
);
CREATE INDEX idx_backup_events_resource
ON backup_events(
    resource_type,
    resource_key,
    observed_at
);

INSERT INTO backup_events (id, observation_id, resource_type, resource_key, outcome, baseline_state, changes_json, observed_at, recorded_at)
SELECT id, observation_id, resource_type, resource_key, outcome, baseline_state, changes_json, observed_at, recorded_at FROM backup_events_old;

-- table: backup_incidents
CREATE TABLE backup_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    resource_type TEXT NOT NULL
        CHECK (
            resource_type IN (
                'backup_job',
                'backup_guest',
                'backup_scheduled_run',
                'backup_timemachine',
                'backup_phone',
                'backup_messages',
                'backup_host_verify',
                'backup_rsync_filebackups'
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
CREATE UNIQUE INDEX idx_backup_incidents_one_open
ON backup_incidents(
    resource_type,
    resource_key,
    incident_type
)
WHERE incident_state = 'OPEN';
CREATE INDEX idx_backup_incidents_state
ON backup_incidents(
    incident_state,
    updated_at
);
CREATE INDEX idx_backup_incidents_resource
ON backup_incidents(
    resource_type,
    resource_key,
    opened_at
);

INSERT INTO backup_incidents (id, resource_type, resource_key, display_name, incident_type, incident_state, baseline_state, opened_event_id, last_event_id, opened_observation_id, last_abnormal_observation_id, recovered_observation_id, opened_at, last_abnormal_at, recovered_at, occurrence_count, opening_changes_json, latest_changes_json, note, created_at, updated_at)
SELECT id, resource_type, resource_key, display_name, incident_type, incident_state, baseline_state, opened_event_id, last_event_id, opened_observation_id, last_abnormal_observation_id, recovered_observation_id, opened_at, last_abnormal_at, recovered_at, occurrence_count, opening_changes_json, latest_changes_json, note, created_at, updated_at FROM backup_incidents_old;

-- keep AUTOINCREMENT counters so ids of deleted rows are never reused
DELETE FROM sqlite_sequence WHERE name IN ('backup_events', 'backup_incidents');
INSERT INTO sqlite_sequence(name, seq)
SELECT 'backup_events', seq FROM sqlite_sequence WHERE name = 'backup_events_old';
INSERT INTO sqlite_sequence(name, seq)
SELECT 'backup_incidents', seq FROM sqlite_sequence WHERE name = 'backup_incidents_old';

DROP TABLE backup_incidents_old;
DROP TABLE backup_events_old;

INSERT INTO metadata(key, value)
VALUES ('backup_ledger_schema', '2')
ON CONFLICT(key) DO UPDATE SET value=excluded.value;
