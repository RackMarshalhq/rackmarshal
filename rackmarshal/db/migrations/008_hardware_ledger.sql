-- RackMarshal HARDWARE ledger parity Step C — additive empty tables (2026-09-17)
-- Design: packaging/HARDWARE_LEDGER_PARITY.md
-- Does NOT change cycle, notify, or specialized temperature tables.
-- Processing cursor: observation watermark (legacy implementation note), not per-incident rows.

CREATE TABLE IF NOT EXISTS hardware_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    serial TEXT NOT NULL,
    role TEXT NOT NULL,
    model TEXT,
    outcome TEXT NOT NULL
        CHECK (outcome IN (
            'OPENED',
            'ESCALATED',
            'RECOVERED',
            'MISSING',
            'OK'
        )),
    severity TEXT
        CHECK (
            severity IS NULL
            OR severity IN ('HOT', 'URGENT', 'MISSING')
        ),
    temperature_c REAL,
    changes_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (observation_id) REFERENCES hardware_observations(id) ON DELETE RESTRICT,
    UNIQUE (observation_id, serial, outcome)
);

CREATE INDEX IF NOT EXISTS idx_hardware_events_serial
    ON hardware_events(serial, observed_at);
CREATE INDEX IF NOT EXISTS idx_hardware_events_observation
    ON hardware_events(observation_id);

CREATE TABLE IF NOT EXISTS hardware_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial TEXT NOT NULL,
    role TEXT NOT NULL,
    model TEXT,
    incident_type TEXT NOT NULL
        CHECK (incident_type IN (
            'HARDWARE_TEMP_HOT',
            'HARDWARE_TEMP_URGENT',
            'HARDWARE_MISSING'
        )),
    severity TEXT NOT NULL
        CHECK (severity IN ('HOT', 'URGENT', 'MISSING')),
    incident_state TEXT NOT NULL
        CHECK (incident_state IN ('OPEN', 'RECOVERED')),
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
    FOREIGN KEY (opened_event_id) REFERENCES hardware_events(id) ON DELETE RESTRICT,
    FOREIGN KEY (last_event_id) REFERENCES hardware_events(id) ON DELETE RESTRICT,
    FOREIGN KEY (opened_observation_id) REFERENCES hardware_observations(id) ON DELETE RESTRICT,
    FOREIGN KEY (last_abnormal_observation_id) REFERENCES hardware_observations(id) ON DELETE RESTRICT,
    FOREIGN KEY (recovered_observation_id) REFERENCES hardware_observations(id) ON DELETE RESTRICT,
    CHECK (
        (incident_state = 'OPEN' AND recovered_observation_id IS NULL AND recovered_at IS NULL)
        OR
        (incident_state = 'RECOVERED' AND recovered_observation_id IS NOT NULL AND recovered_at IS NOT NULL)
    )
);

-- At most one OPEN incident per NVMe serial (escalations update the same row).
CREATE UNIQUE INDEX IF NOT EXISTS idx_hardware_incidents_one_open
    ON hardware_incidents(serial)
    WHERE incident_state = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_hardware_incidents_state
    ON hardware_incidents(incident_state, updated_at);

-- Observation watermark cursor (source of truth for processor idempotency).
CREATE TABLE IF NOT EXISTS hardware_incident_processing (
    processor_key TEXT PRIMARY KEY,
    last_processed_observation_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (last_processed_observation_id)
        REFERENCES hardware_observations(id)
        ON DELETE RESTRICT
);

INSERT OR IGNORE INTO hardware_incident_processing (
    processor_key,
    last_processed_observation_id
) VALUES (
    'hardware_incident_processor',
    NULL
);

INSERT OR REPLACE INTO metadata(key, value) VALUES
    ('hardware_ledger_schema', '1'),
    ('hardware_ledger_applied_at', strftime('%Y-%m-%dT%H:%M:%fZ','now'));
