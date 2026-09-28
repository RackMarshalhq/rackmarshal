-- PVE ledger: observations, baselines, events, incidents, processing
-- fresh-host drill F2 2026-09-17; CREATE IF NOT EXISTS from CT 110 live schema

-- table: observations
CREATE TABLE IF NOT EXISTS observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collector       TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    source          TEXT NOT NULL,
    schema_version  INTEGER NOT NULL,
    tls_verified    INTEGER NOT NULL CHECK (tls_verified IN (0,1)),
    resource_count  INTEGER NOT NULL CHECK (resource_count >= 0),
    payload_json    TEXT NOT NULL,
    recorded_at     TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    )
);
CREATE INDEX IF NOT EXISTS idx_observations_collector_observed_at
    ON observations (collector, observed_at);

-- table: resource_baseline
CREATE TABLE IF NOT EXISTS resource_baseline (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_type       TEXT NOT NULL,
    resource_key        TEXT NOT NULL,
    display_name        TEXT,
    expected_status     TEXT NOT NULL,
    baseline_state      TEXT NOT NULL
                        CHECK (
                            baseline_state IN (
                                'VERIFIED',
                                'EXPECTED',
                                'KNOWN-ISSUE',
                                'FAILED',
                                'DECOMMISSIONED'
                            )
                        ),
    source_observation  INTEGER,
    note                TEXT,
    created_at          TEXT NOT NULL DEFAULT (
                            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        ),
    updated_at          TEXT NOT NULL DEFAULT (
                            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        ),

    UNIQUE (resource_type, resource_key),

    FOREIGN KEY (source_observation)
        REFERENCES observations(id)
);
CREATE INDEX IF NOT EXISTS idx_resource_baseline_state
    ON resource_baseline (baseline_state);

-- table: resource_events
CREATE TABLE IF NOT EXISTS resource_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    observation_id      INTEGER NOT NULL,

    event_type          TEXT NOT NULL
                        CHECK (
                            event_type IN (
                                'STATUS-CHANGED',
                                'MISSING',
                                'NEW'
                            )
                        ),

    resource_type       TEXT NOT NULL,
    resource_key        TEXT NOT NULL,
    display_name        TEXT,

    baseline_state      TEXT
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

    expected_status     TEXT,
    actual_status       TEXT,

    note                TEXT,

    detected_at         TEXT NOT NULL DEFAULT (
                            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        ),

    FOREIGN KEY (observation_id)
        REFERENCES observations(id),

    UNIQUE (
        observation_id,
        event_type,
        resource_type,
        resource_key
    )
);
CREATE INDEX IF NOT EXISTS idx_resource_events_observation
    ON resource_events (observation_id);
CREATE INDEX IF NOT EXISTS idx_resource_events_resource
    ON resource_events (
        resource_type,
        resource_key,
        detected_at
    );
CREATE INDEX IF NOT EXISTS idx_resource_events_type
    ON resource_events (
        event_type,
        detected_at
    );

-- table: resource_incidents
CREATE TABLE IF NOT EXISTS resource_incidents (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,

    resource_type               TEXT NOT NULL,
    resource_key                TEXT NOT NULL,
    display_name                TEXT,

    incident_type               TEXT NOT NULL
                                CHECK (
                                    incident_type IN (
                                        'STATUS-CHANGED',
                                        'MISSING',
                                        'NEW'
                                    )
                                ),

    incident_state              TEXT NOT NULL
                                CHECK (
                                    incident_state IN (
                                        'OPEN',
                                        'RECOVERED'
                                    )
                                ),

    baseline_state              TEXT
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

    expected_status             TEXT,
    abnormal_status             TEXT,

    opened_observation_id       INTEGER NOT NULL,
    last_abnormal_observation_id INTEGER NOT NULL,
    recovered_observation_id    INTEGER,

    opened_at                   TEXT NOT NULL,
    last_abnormal_at            TEXT NOT NULL,
    recovered_at                TEXT,

    occurrence_count            INTEGER NOT NULL DEFAULT 1
                                CHECK (occurrence_count >= 1),

    note                        TEXT,

    created_at                  TEXT NOT NULL DEFAULT (
                                    strftime(
                                        '%Y-%m-%dT%H:%M:%fZ',
                                        'now'
                                    )
                                ),

    updated_at                  TEXT NOT NULL DEFAULT (
                                    strftime(
                                        '%Y-%m-%dT%H:%M:%fZ',
                                        'now'
                                    )
                                ),

    FOREIGN KEY (opened_observation_id)
        REFERENCES observations(id),

    FOREIGN KEY (last_abnormal_observation_id)
        REFERENCES observations(id),

    FOREIGN KEY (recovered_observation_id)
        REFERENCES observations(id),

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
CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_incidents_one_open
    ON resource_incidents (
        resource_type,
        resource_key
    )
    WHERE incident_state = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_resource_incidents_state
    ON resource_incidents (
        incident_state,
        updated_at
    );
CREATE INDEX IF NOT EXISTS idx_resource_incidents_resource
    ON resource_incidents (
        resource_type,
        resource_key,
        opened_at
    );
CREATE INDEX IF NOT EXISTS idx_resource_incidents_opened_observation
    ON resource_incidents (
        opened_observation_id
    );
CREATE INDEX IF NOT EXISTS idx_resource_incidents_last_abnormal_observation
    ON resource_incidents (
        last_abnormal_observation_id
    );
CREATE INDEX IF NOT EXISTS idx_resource_incidents_recovered_observation
    ON resource_incidents (
        recovered_observation_id
    );

-- table: incident_processing
CREATE TABLE IF NOT EXISTS incident_processing (
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
        strftime(
            '%Y-%m-%dT%H:%M:%fZ',
            'now'
        )
    ),
    note TEXT,
    FOREIGN KEY (observation_id)
        REFERENCES observations(id)
);
CREATE INDEX IF NOT EXISTS idx_incident_processing_processed_at
ON incident_processing(processed_at);

