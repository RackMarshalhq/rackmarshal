-- RackMarshal HARDWARE ledger Step C→D correction (2026-09-17)
-- Replace per-incident hardware_incident_processing with observation watermark cursor.
-- Safe if Step C never applied the old shape, or if already on cursor shape.

-- Detect old shape: had incident_id PK (per-incident). New shape: processor_key PK.
-- SQLite cannot ALTER easily; DROP + recreate when old columns present.

DROP TABLE IF EXISTS hardware_incident_processing;

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
    ('hardware_ledger_processing_cursor', 'observation_watermark_v1'),
    ('hardware_ledger_008b_applied_at', strftime('%Y-%m-%dT%H:%M:%fZ','now'));
