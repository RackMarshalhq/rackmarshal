# RackMarshal 1.1 — Incident Summary and Detail Page Contract

Status: **FROZEN IMPLEMENTATION CONTRACT**
Date: 2026-09-29

## Deterministic summary API

Endpoint: `GET /v1/incidents/{incident_id}/summary`

The summary is derived only from the normalized incident, incident timeline, and evidence bundle. It MUST NOT use an AI model and MUST NOT infer root cause, severity, or recovery.

Required fields:
- `incident_id`, `domain`, `resource_type`, `resource_key`, `state`
- `headline`: concise deterministic status sentence
- `opened_statement`
- `latest_statement`
- `recovery_statement`
- `cause_statement`
- `evidence_refs`: stable canonical refs used by the summary
- `provenance`
- `authority: DERIVED`

For open incidents, `recovery_statement` MUST be exactly `No recovery is recorded.` For recovered incidents it MUST cite the recorded recovery time. `cause_statement` MUST state that RackMarshal does not establish root cause unless a future authoritative ledger field explicitly does so.

## Human incident page

Route: `GET /incidents/{incident_id}`

The page is local/read-only and renders the same deterministic data used by the API. It MUST show:
- incident identity, domain/resource, and OPEN/RECOVERED state;
- deterministic summary;
- ordered timeline;
- expandable/visible evidence references;
- provenance/linkage mode;
- no write/acknowledge/close/restart controls.

All ledger-derived text MUST be HTML-escaped. No raw `payload_json`, credentials, or arbitrary host data may be rendered.

## Promotion gate

The page/API remain local first. They are not added to the public website and do not change the MCP surface. Production promotion requires fixture tests plus real-data HTTP smoke tests for an open direct-linkage incident, recovered direct-linkage incident, and PVE legacy incident.
