# RackMarshal API v1.1 — Incident Timeline Contract

Status: **FROZEN IMPLEMENTATION CONTRACT**
Date: 2026-09-29

## Endpoint

`GET /v1/incidents/{incident_id}/timeline`

## Purpose

Return a deterministic, ordered lifecycle for one RackMarshal incident without generating causal narrative. The timeline is assembled from the incident ledger, matching domain event ledger, and authoritative observation references.

## Identity and authority

- `incident_id` MUST be canonical, e.g. `BACKUP:29`.
- Timeline items MUST use stable domain-qualified event/observation IDs.
- Timeline facts are `OBSERVED` or `DERIVED`; AI interpretation is not part of this endpoint.
- No severity or cause is invented when absent from the source ledger.

## Response shape

```json
{
  "incident_id": "BACKUP:29",
  "domain": "BACKUP",
  "resource_type": "backup_phone",
  "resource_key": "user_c",
  "state": "OPEN",
  "opened_at": "2026-09-27T14:22:24.258895Z",
  "last_abnormal_at": "2026-09-30T02:08:32.908707Z",
  "recovered_at": null,
  "items": [],
  "authority": "DERIVED"
}
```

Each item MUST include: `kind`, `timestamp`, `authority`, and applicable `event_id`, `observation_id`, `changes`, `evidence_refs`.

## Required lifecycle item kinds

- `INCIDENT_OPENED`
- `MATERIAL_CHANGE`
- `LAST_ABNORMAL`
- `INCIDENT_RECOVERED` when recovery exists

## Domain linkage rules

- ZFS, BACKUP, HA, HARDWARE, MOUNT: use incident `opened_event_id` and `last_event_id` when present, plus matching resource events between incident bounds.
- PVE: legacy incident rows do not contain event IDs. Correlate deterministically by `resource_type`, `resource_key`, lifecycle timestamps, and authoritative observation IDs. This limitation MUST be represented in provenance metadata; do not invent event linkage.
- Repeated polling observations MUST be compacted into material-change runs using the same semantics as `/v1/changes`.
- Recovery is authoritative only when `recovered_observation_id` and `recovered_at` are recorded.

## Ordering

Items are ascending by timestamp. Ties use stable local event/observation ID ordering.

## Error behavior

- malformed numeric-only incident IDs: `400 INVALID_ID`
- unknown canonical incident: `404 INCIDENT_NOT_FOUND`
