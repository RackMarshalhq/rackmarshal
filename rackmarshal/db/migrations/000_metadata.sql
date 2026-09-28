-- RackMarshal base — metadata key/value (required by 007+ INSERT OR REPLACE)
-- Fresh-host drill 2026-09-17: CT 110 grew this from early app code; now explicit.

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
