-- RackMarshal HARDWARE ledger Step G — retire specialized temperature tables (2026-09-17)
-- Replaces hardware_temperature_state streaks with lean hardware_device_state.
-- Drops: hardware_temperature_events, hardware_temperature_notification_state, hardware_temperature_state
-- Fresh-host safe (2026-09-17 drill): ensure legacy table exists (empty) so seed SELECT is valid.

CREATE TABLE IF NOT EXISTS hardware_device_state (
    serial TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    role TEXT NOT NULL,
    hot_streak INTEGER NOT NULL DEFAULT 0 CHECK (hot_streak >= 0),
    cool_streak INTEGER NOT NULL DEFAULT 0 CHECK (cool_streak >= 0),
    last_observed_at TEXT,
    last_temperature_c REAL,
    maximum_temperature_c REAL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- On a live host mid-Step-G this is a no-op (table already present with data).
-- On a fresh host this creates an empty stub so the following SELECT succeeds.
CREATE TABLE IF NOT EXISTS hardware_temperature_state (
    serial TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    role TEXT NOT NULL,
    hot_streak INTEGER NOT NULL DEFAULT 0,
    cool_streak INTEGER NOT NULL DEFAULT 0,
    last_observed_at TEXT,
    last_temperature_c REAL,
    maximum_temperature_c REAL
);

INSERT OR IGNORE INTO hardware_device_state (
    serial, model, role, hot_streak, cool_streak,
    last_observed_at, last_temperature_c, maximum_temperature_c
)
SELECT
    serial, model, role, hot_streak, cool_streak,
    last_observed_at, last_temperature_c, maximum_temperature_c
FROM hardware_temperature_state;

DROP TABLE IF EXISTS hardware_temperature_notification_state;
DROP TABLE IF EXISTS hardware_temperature_events;
DROP TABLE IF EXISTS hardware_temperature_state;

INSERT OR REPLACE INTO metadata(key, value) VALUES
    ('hardware_ledger_temp_tables', 'retired_stepG'),
    ('hardware_ledger_stepG_applied_at', strftime('%Y-%m-%dT%H:%M:%fZ','now'));
