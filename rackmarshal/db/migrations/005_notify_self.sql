-- Shared notify + self-incidents ledgers
-- fresh-host drill F2 2026-09-17; CREATE IF NOT EXISTS from CT 110 live schema

-- table: incident_notifications
CREATE TABLE IF NOT EXISTS incident_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_domain TEXT NOT NULL CHECK (source_domain IN ('PVE', 'ZFS', 'BACKUP', 'HA', 'SELF', 'HARDWARE', 'MOUNT')),
    incident_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL
        CHECK (notification_type IN ('OPENED', 'RECOVERED')),
    delivery_state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (delivery_state IN ('PENDING', 'SENT', 'FAILED')),
    late_discovery INTEGER NOT NULL DEFAULT 0 CHECK (late_discovery IN (0,1)),
    packet_json TEXT,
    explanation_json TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_attempt_at TEXT,
    delivered_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source_domain, incident_id, notification_type),
    CHECK (
        (delivery_state='SENT' AND delivered_at IS NOT NULL)
        OR
        (delivery_state!='SENT' AND delivered_at IS NULL)
    )
);

-- table: self_incidents
CREATE TABLE IF NOT EXISTS self_incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_key TEXT NOT NULL,
        incident_type TEXT NOT NULL
            CHECK (
                incident_type IN (
                    'FRESHNESS_STALE',
                    'FRESHNESS_MISSING',
                    'UNIT_FAILED',
                    'UNIT_INACTIVE',
                    'NOTIFY_FAILED',
                    'NOTIFY_BACKLOG'
                )
            ),
        severity TEXT NOT NULL
            CHECK (
                severity IN (
                    'info',
                    'warning',
                    'critical',
                    'urgent'
                )
            ),
        incident_state TEXT NOT NULL
            CHECK (
                incident_state IN ('OPEN', 'RECOVERED')
            ),
        detail_json TEXT,
        opened_at TEXT NOT NULL
            DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
        recovered_at TEXT,
        last_seen_at TEXT NOT NULL
            DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
        UNIQUE (signal_key),
        CHECK (
            (
                incident_state = 'OPEN'
                AND recovered_at IS NULL
            )
            OR
            (
                incident_state = 'RECOVERED'
                AND recovered_at IS NOT NULL
            )
        )
    );
CREATE INDEX IF NOT EXISTS idx_self_incidents_state
    ON self_incidents (incident_state)
    ;

