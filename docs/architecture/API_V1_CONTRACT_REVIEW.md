# API v1 Contract Review

Status: **FROZEN IMPLEMENTATION CONTRACT**
Date: 2026-09-29

## Review result

The API v1 surface is implementable over the current RackMarshal ledgers without changing the authoritative domain schemas. The service layer MUST normalize the six domain-specific ledgers; clients never receive table names or depend on SQLite layout.

Two corrections are required from the earlier draft: incident IDs are only unique inside a domain ledger, so public incident identity is `{domain}:{id}`; and `severity` is not uniformly stored by PVE/ZFS/BACKUP/HA, so the API MUST NOT invent it. When unavailable, `severity` is `null` with authority `UNKNOWN`.

## Canonical public identities

- Domain: `PVE`, `ZFS`, `BACKUP`, `HA`, `HARDWARE`, `MOUNT`.
- Observation: `{domain}:{id}`, for example `ZFS:9912`.
- Event/change: `{domain}:{id}`.
- Incident: `{domain}:{id}`, for example `ZFS:47`.
- Evidence: `observation:ZFS:9912`, `event:ZFS:314`, or `incident:ZFS:47`.

Numeric database IDs MAY be returned as `local_id`, but clients SHALL use canonical IDs.

## Common envelope

Every successful JSON response uses `api_version`, `generated_at`, `data`, and `meta`. Collection `meta` includes `limit` and `next_cursor`; `total` is optional. Errors use the v1 error envelope defined in `API_V1_SCHEMA.md`.
## Endpoint contracts

### GET /v1/health
API process/readability health, not infrastructure health. Data: `status`, `database_readable`, `api_version`. DB failure returns `503 SERVICE_UNAVAILABLE`.

### GET /v1/status
Normalized infrastructure summary: `overall_status`, `domains[]`, `open_incident_count`, `generated_from`. Status is deterministic, never an AI assessment.

### GET /v1/domains and /v1/domains/{domain}
Domain summaries expose `domain`, `status`, `last_observation`, `freshness`, `open_incident_count`, `authority`, and available `cycle_health`. Unknown domains return `404 DOMAIN_NOT_FOUND`. The bounded domain list is not paginated.

### GET /v1/incidents
Filters: `domain`, `state`, `resource_type`, `resource_key`, `opened_after`, `opened_before`, `limit`, `cursor`. Default is all domains/states, newest first. `state` accepts `OPEN|RECOVERED`.

### GET /v1/incidents/{incident_id}
Requires canonical ID such as `ZFS:47`. Returns the normalized incident, opening/latest changes, and evidence references. Numeric-only IDs return `400 INVALID_ID` because they are ambiguous across ledgers.

### GET /v1/observations
Filters: `domain`, `collector`, `observed_after`, `observed_before`, `limit`, `cursor`. Returns metadata by default; raw `payload_json` is not part of the public collection contract.

### GET /v1/events and /v1/changes
Filters: `domain`, `resource_type`, `resource_key`, `observed_after`, `observed_before`, `limit`, `cursor`. `/v1/events` remains the forensic event stream. `/v1/changes` is investigation-oriented: repeated polling observations of the same condition are collapsed per resource into a material-change run with first/latest timestamps, first/latest values, repeat count, and first/latest evidence references. A transition away from a condition and back creates a new run. The adapter never generates narrative explanations.
### GET /v1/evidence/{evidence_ref}
Accepts typed evidence refs and returns normalized metadata plus structured `content`. Secrets and credentials MUST be redacted. Unknown refs return `404 EVIDENCE_NOT_FOUND`.

### GET /v1/recoveries
Filters: `domain`, `recovered_after`, `recovered_before`, `limit`, `cursor`. This is a view over `RECOVERED` incidents; no new recovery table is required. Recovery evidence points to `recovered_observation_id`.

### GET /v1/backups/status
Deterministic BACKUP summary derived from the latest `backup_domain` observation and backup incident ledger; not a general raw-payload endpoint.

## Domain adapter map

| Domain | Observation source | Event source | Incident source | Recovery proof |
|---|---|---|---|---|
| PVE | `observations` / `pve_cluster_resources` | `resource_events` | `resource_incidents` | `recovered_observation_id` |
| ZFS | `zfs_observations` | `zfs_events` | `zfs_incidents` | `recovered_observation_id` |
| BACKUP | `observations` / `backup_domain` | `backup_events` | `backup_incidents` | `recovered_observation_id` |
| HA | `observations` / HA collector | `ha_events` | `ha_incidents` | `recovered_observation_id` |
| HARDWARE | `hardware_observations` | `hardware_events` | `hardware_incidents` | `recovered_observation_id` |
| MOUNT | `mount_observations` | `mount_events` | `mount_incidents` | `recovered_observation_id` |

## Canonical incident object

Required fields: `id`, `local_id`, `domain`, `resource_type`, `resource_key`, `display_name`, `incident_type`, `state`, `severity`, `baseline_state`, `opened_at`, `last_abnormal_at`, `recovered_at`, `occurrence_count`, `authority`, `evidence_refs`.

`severity` is nullable. The API MUST preserve domain-native incident/event types rather than coercing them into a lossy global enum.
## Freshness and status

Freshness thresholds continue to come from RackMarshal's deterministic status/self-watch logic. API v1 exposes the result; it does not introduce model judgment. `UNKNOWN` is used when required evidence is unavailable.

## Raw payload policy

Raw collector payloads are internal evidence, not the default public API. A typed evidence request MAY expose a sanitized structured subset when needed for investigation. API v1 MUST NOT return credentials, tokens, secret configuration, or unrestricted host data merely because it exists in `payload_json`.

## Cursor contract

Cursors are opaque and MUST NOT expose SQL fragments. Default limit is 50; maximum is 200. Invalid or expired cursors return `400 INVALID_CURSOR`.

## Time contract

All public timestamps are UTC RFC 3339/ISO-8601 strings ending in `Z`. Filters are inclusive at the lower bound and exclusive at the upper bound: `after <= t < before`.

## Contract-test gate

Before API v1 is stable, tests SHALL prove canonical ID uniqueness across domains; open/recovered lifecycle mapping; recovery evidence mapping; nullable severity; pagination/cursor rejection; time/domain filtering; missing/unknown data behavior; raw-payload redaction; and compatibility of legacy `/health` and `/status`.