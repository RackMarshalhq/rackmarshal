-- RackMarshal HARDWARE observations (prerequisite for 008 FK)
-- Fresh-host drill 2026-09-17: previously created only by run_hardware_cycle.initialize_db.

CREATE TABLE IF NOT EXISTS hardware_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL,
    host TEXT NOT NULL,
    serial TEXT NOT NULL,
    model TEXT,
    role TEXT NOT NULL,
    nvme TEXT,
    temperature_c REAL,
    present INTEGER NOT NULL
        CHECK (present IN (0, 1)),
    status TEXT NOT NULL
        CHECK (
            status IN (
                'OK',
                'HOT',
                'URGENT',
                'MISSING'
            )
        ),
    recorded_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    )
);
CREATE INDEX IF NOT EXISTS idx_hardware_observations_serial_time
    ON hardware_observations (serial, observed_at);

INSERT OR REPLACE INTO metadata (key, value) VALUES
    ('hardware_observations_schema', '1'),
    ('hardware_observations_applied_at', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
