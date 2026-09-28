-- RackMarshal 010_cycle_health
-- Durable systemd cycle execution health for self-watch.

CREATE TABLE IF NOT EXISTS cycle_health (
    unit_name TEXT PRIMARY KEY,
    health_state TEXT NOT NULL
        CHECK (health_state IN ('SUCCESS', 'FAILED')),
    last_result_at TEXT NOT NULL,
    last_success_at TEXT,
    last_failure_at TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_exit_code INTEGER,
    last_exit_status INTEGER,
    detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_cycle_health_state
    ON cycle_health(health_state);

INSERT INTO metadata(key, value)
VALUES ('cycle_health_schema', '1')
ON CONFLICT(key) DO UPDATE SET value=excluded.value;
