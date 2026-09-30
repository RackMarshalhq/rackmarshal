# RackMarshal API v1 Schema

Status: **FROZEN CONTRACT BASELINE — IMPLEMENTATION MAY BEGIN AFTER SCHEMA REVIEW GATE**
Date: 2026-09-29

## Common envelope

Every successful v1 JSON response SHALL use this envelope unless an endpoint is explicitly documented otherwise:

```json
{
  "api_version": "v1",
  "generated_at": "2026-09-29T23:00:00Z",
  "data": {},
  "meta": {}
}
```

## Authority model

Operational facts exposed through v1 SHALL carry one of:

- `OBSERVED` — directly recorded by RackMarshal collection.
- `DERIVED` — deterministically calculated from recorded state.
- `EXPECTED` — configured or declared expected state.
- `ADVISORY` — human/AI interpretation; not authoritative state.
- `UNKNOWN` — insufficient evidence.

## Incident object

```json
{
  "id": "ZFS:47",
  "local_id": 47,
  "domain": "ZFS",
  "resource_type": "pool",
  "resource_key": "data",
  "incident_type": "state_change",
  "state": "OPEN",
  "severity": "warning",
  "opened_at": "2026-09-29T21:15:00Z",
  "last_abnormal_at": "2026-09-29T21:15:00Z",
  "occurrence_count": 1,
  "authority": "OBSERVED",
  "evidence_refs": []
}
```

## Domain status object

```json
{
  "domain": "ZFS",
  "status": "PROBLEM",
  "open_incident_count": 1,
  "last_observation_at": "2026-09-29T21:15:00Z",
  "freshness": "OK",
  "authority": "DERIVED"
}
```

## Observation reference

```json
{
  "id": "ZFS:9912",
  "local_id": 9912,
  "domain": "ZFS",
  "collector": "zfs",
  "observed_at": "2026-09-29T21:15:00Z",
  "source": "observer-host",
  "authority": "OBSERVED"
}
```

## Evidence object

```json
{
  "id": "observation:ZFS:9912",
  "kind": "observation",
  "authority": "OBSERVED",
  "observed_at": "2026-09-29T21:15:00Z",
  "source_ref": "observation:ZFS:9912",
  "summary": "Recorded operational evidence"
}
```

## Recovery object

```json
{
  "incident_id": "ZFS:47",
  "state": "VERIFIED",
  "verified_at": "2026-09-29T22:40:00Z",
  "verification_source": "rackmarshal",
  "authority": "OBSERVED",
  "evidence_refs": ["observation:ZFS:10004"]
}
```

## Change object

```json
{
  "id": "ZFS:314",
  "local_id": 314,
  "domain": "ZFS",
  "resource_key": "data",
  "change_type": "state_change",
  "observed_at": "2026-09-29T21:15:00Z",
  "authority": "DERIVED",
  "evidence_refs": ["observation:ZFS:9912"]
}
```

## Pagination

Collection responses SHALL expose `limit` and `next_cursor`; `total` MAY be included when efficiently available. Cursors are opaque to clients.

## Error object

```json
{
  "api_version": "v1",
  "error": {
    "code": "NOT_FOUND",
    "message": "Incident not found"
  }
}
```

## Compatibility

Fields may be added within v1. Existing field meaning SHALL NOT change within v1. Breaking semantic changes require a new API version.

## Schema review gate

Before API v1 implementation is considered contract-complete, each endpoint SHALL have a documented response shape, filter/query parameters, pagination behavior, error cases, authority/provenance semantics, and at least one representative example derived from the existing RackMarshal data model. Implementation MAY prototype behind this contract, but no endpoint is declared stable until this gate passes.
