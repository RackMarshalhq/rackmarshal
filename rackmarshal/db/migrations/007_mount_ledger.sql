-- RackMarshal MOUNT Step M3 — ledger tables (2026-09-17)
-- Catalog-driven mount monitoring; collectors not wired yet.

CREATE TABLE IF NOT EXISTS mount_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    catalog_version TEXT,
    checked_count INTEGER NOT NULL CHECK (checked_count >= 0),
    ok_count INTEGER NOT NULL CHECK (ok_count >= 0),
    problem_count INTEGER NOT NULL CHECK (problem_count >= 0),
    payload_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_mount_observations_observed_at
    ON mount_observations(observed_at);

CREATE TABLE IF NOT EXISTS mount_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    mount_id TEXT NOT NULL,
    guest_kind TEXT NOT NULL
        CHECK (guest_kind IN ('host','lxc','qemu')),
    guest_id TEXT NOT NULL,
    mountpoint TEXT NOT NULL,
    outcome TEXT NOT NULL
        CHECK (outcome IN (
            'MISSING',
            'WRONG_SOURCE',
            'UNREADABLE',
            'UNEXPECTED',
            'EXPORT_STALE',
            'RECOVERED',
            'OK'
        )),
    expected_source TEXT,
    observed_source TEXT,
    fstype TEXT,
    changes_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (observation_id) REFERENCES mount_observations(id) ON DELETE RESTRICT,
    UNIQUE (observation_id, mount_id, outcome)
);
CREATE INDEX IF NOT EXISTS idx_mount_events_mount
    ON mount_events(mount_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_mount_events_observation
    ON mount_events(observation_id);

CREATE TABLE IF NOT EXISTS mount_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mount_id TEXT NOT NULL,
    guest_kind TEXT NOT NULL
        CHECK (guest_kind IN ('host','lxc','qemu')),
    guest_id TEXT NOT NULL,
    mountpoint TEXT NOT NULL,
    display_name TEXT NOT NULL,
    incident_type TEXT NOT NULL
        CHECK (incident_type IN (
            'MOUNT_MISSING',
            'MOUNT_WRONG_SOURCE',
            'MOUNT_UNREADABLE',
            'MOUNT_UNEXPECTED',
            'MOUNT_EXPORT_STALE'
        )),
    severity TEXT NOT NULL
        CHECK (severity IN ('info','warning','critical','urgent')),
    incident_state TEXT NOT NULL
        CHECK (incident_state IN ('OPEN','RECOVERED')),
    opened_event_id INTEGER NOT NULL,
    last_event_id INTEGER NOT NULL,
    opened_observation_id INTEGER NOT NULL,
    last_abnormal_observation_id INTEGER NOT NULL,
    recovered_observation_id INTEGER,
    opened_at TEXT NOT NULL,
    last_abnormal_at TEXT NOT NULL,
    recovered_at TEXT,
    occurrence_count INTEGER NOT NULL DEFAULT 1 CHECK (occurrence_count >= 1),
    opening_changes_json TEXT NOT NULL,
    latest_changes_json TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (opened_event_id) REFERENCES mount_events(id) ON DELETE RESTRICT,
    FOREIGN KEY (last_event_id) REFERENCES mount_events(id) ON DELETE RESTRICT,
    FOREIGN KEY (opened_observation_id) REFERENCES mount_observations(id) ON DELETE RESTRICT,
    FOREIGN KEY (last_abnormal_observation_id) REFERENCES mount_observations(id) ON DELETE RESTRICT,
    FOREIGN KEY (recovered_observation_id) REFERENCES mount_observations(id) ON DELETE RESTRICT,
    CHECK (
        (incident_state = 'OPEN' AND recovered_observation_id IS NULL AND recovered_at IS NULL)
        OR
        (incident_state = 'RECOVERED' AND recovered_observation_id IS NOT NULL AND recovered_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mount_incidents_one_open
    ON mount_incidents(mount_id, incident_type)
    WHERE incident_state = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_mount_incidents_state
    ON mount_incidents(incident_state, updated_at);

CREATE TABLE IF NOT EXISTS mount_incident_processing (
    incident_id INTEGER PRIMARY KEY,
    last_processed_event_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (incident_id) REFERENCES mount_incidents(id) ON DELETE CASCADE
);

INSERT OR REPLACE INTO metadata(key, value) VALUES
    ('mount_ledger_schema', '1'),
    ('mount_ledger_applied_at', strftime('%Y-%m-%dT%H:%M:%fZ','now'));
