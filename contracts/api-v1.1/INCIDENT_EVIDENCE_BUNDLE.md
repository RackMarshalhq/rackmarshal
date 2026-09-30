# RackMarshal API v1.1 — Incident Evidence Bundle Contract

Status: **FROZEN IMPLEMENTATION CONTRACT**
Date: 2026-09-29

## Endpoint

`GET /v1/incidents/{incident_id}/evidence-bundle`

## Purpose

Return one compact, bounded, deterministic evidence package for a single incident. The bundle exists to reduce multi-call investigation overhead for both humans and agents without creating a second source of truth.

## Response sections

The top-level `data` object MUST contain:

- `incident`: canonical normalized incident object.
- `timeline`: the deterministic incident timeline defined by `INCIDENT_TIMELINE.md`.
- `opening_evidence`: sanitized typed evidence for the opening observation and opening event when authoritative linkage exists.
- `latest_abnormal_evidence`: sanitized typed evidence for the latest abnormal observation and event when authoritative linkage exists.
- `recovery_evidence`: sanitized typed recovery observation/event evidence, or `null` for an open incident.
- `material_changes`: compact incident-bounded material-change runs.
- `provenance`: domain linkage mode, authoritative IDs used, and any explicit linkage limitations.
- `authority`: `DERIVED`.

## Bounding rules

- The bundle is incident-scoped. It MUST NOT include unrelated resource history outside the incident lifecycle.
- Event search lower bound is the incident's `opened_at`.
- Event search upper bound is `recovered_at` for recovered incidents; otherwise the incident's `last_abnormal_at` or current query time where explicitly required.
- Material changes MUST use compaction semantics from `/v1/changes`.
- Default maximum material-change runs: 50.
- Bundle construction MUST NOT expose raw collector `payload_json`.

## Evidence rules

- Typed evidence refs use `observation:{DOMAIN}:{id}`, `event:{DOMAIN}:{id}`, and `incident:{DOMAIN}:{id}`.
- Secrets, credentials, raw configuration secrets, and unrestricted host payloads remain redacted.
- Missing evidence linkage is represented as `null` or an explicit provenance limitation, never synthesized.
- Recovery evidence is only present when RackMarshal has authoritative recovery fields.

## Provenance linkage modes

- `DIRECT_EVENT_IDS`: incident row contains opened/last event IDs and event linkage can be verified directly.
- `LEGACY_RESOURCE_TIME_CORRELATION`: used only where the ledger lacks direct event IDs, currently PVE; correlation is deterministic but explicitly marked as legacy linkage.
- `OBSERVATION_ONLY`: permitted when an authoritative observation exists but no event can be linked.

## Error behavior

- malformed numeric-only incident IDs: `400 INVALID_ID`
- unknown canonical incident: `404 INCIDENT_NOT_FOUND`
