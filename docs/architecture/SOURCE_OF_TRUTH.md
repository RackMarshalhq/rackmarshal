# RackMarshal Source of Truth

Date: 2026-09-29
Status: **AUTHORITATIVE PROJECT SOT**

## VERIFIED

- RackMarshal 1.0.0 is the stable public release.
- RackMarshal Core records durable operational state locally in SQLite.
- Current operational domains include PVE, ZFS, backup, Home Assistant, hardware, and mounts.
- The existing status service exposes local `/health` and `/status` endpoints.
- The current status API is read-only.
- AI explanation data already present in status output is advisory and non-authoritative.
- A six-domain RackMarshal 1.1 production candidate has been qualified under the existing gate documents.

## FROZEN ARCHITECTURE DECISIONS

- RackMarshal Core remains fully usable without AI.
- AI consumes RackMarshal truth; AI does not define RackMarshal truth.
- External integrations use stable API/MCP contracts, not private SQLite schema.
- API v1 begins read-only.
- MCP v1 begins read-only.
- Recovery is authoritative only after independent RackMarshal observation.
- Agent access is deny-by-default and capability-scoped.
- Provider independence is a product requirement.
- Consequential actions require policy-defined authority and audit evidence.

## ACTIVE DEVELOPMENT DIRECTION

The first-class post-1.1 development track is: public API v1 → read-only MCP → provenance/agent contract → investigative agent → controlled actions → agent audit ledger.

## IMPLEMENTATION GATE

No MCP implementation or autonomous-action implementation is authorized by this architecture freeze alone. The next implementation gate is API v1 schema review against the current RackMarshal data model, followed by read-only API implementation and contract tests. Existing RackMarshal 1.1 work remains independent and must not be destabilized by the agent track.


## API V1 SCHEMA REVIEW — 2026-09-29

- **VERIFIED:** The proposed read-only v1 surface can be normalized over the current six domain ledgers without changing their authoritative schemas.
- **FROZEN:** Public observation, event, and incident IDs are domain-qualified because local numeric IDs are not globally unique.
- **FROZEN:** API v1 does not invent severity where a domain ledger does not record it; unavailable severity is `null`/`UNKNOWN`.
- **FROZEN:** Recoveries are a normalized view over recovered incidents and their `recovered_observation_id`; no duplicate recovery authority is introduced.
- **FROZEN:** Raw collector payloads are not default public responses and require sanitization when exposed as typed evidence.
- **NEXT:** Implement the read-only service/adapters and contract tests. MCP remains gated until API v1 passes those tests.


## API V1 IMPLEMENTATION — 2026-09-29

- **VERIFIED:** Read-only API v1 service/adapters are implemented in `rackmarshal/api/v1.py` and routed through the existing status API server without changing legacy `/health` or `/status`.
- **VERIFIED:** v1 implements health, status, domains, incidents, observations, events/changes, evidence, recoveries, and backup status surfaces.
- **VERIFIED:** Domain-qualified public IDs, nullable severity, recovery evidence, opaque pagination, and raw-payload redaction are enforced by contract tests.
- **VERIFIED:** Full unittest discovery passes: 30 tests, including 7 API v1 contract tests and all 23 pre-existing tests.
- **FROZEN:** API v1 remains read-only; MCP is still not implemented.
- **NEXT:** Exercise v1 against a fresh-host/real RackMarshal database, add HTTP-level endpoint smoke tests, then decide whether the API gate is strong enough to begin MCP v1.


## API V1 REAL-DATA / HTTP PROOF — 2026-09-29

- **VERIFIED:** API v1 was run through the real `ThreadingHTTPServer` on isolated loopback port 19110 inside CT 110 against `/var/lib/rackmarshal/state.db` (~108 MB), without replacing or restarting the production listener on 9110.
- **VERIFIED:** Legacy `/health` and `/status` remained compatible; real `/status` and `/v1/status` agreed on `PROBLEM` with 2 open incidents at proof time.
- **VERIFIED:** All v1 read surfaces returned HTTP 200 against accumulated real data: health, status, six domains, incidents, observations, events, changes, recoveries, evidence, and backup status.
- **VERIFIED:** Real-data checks passed for domain-qualified IDs, nullable severity, incident detail, typed recovery/incident evidence, payload redaction, invalid numeric IDs, invalid cursors, unknown domains, domain filtering, and cursor traversal.
- **VERIFIED:** Four HTTP-level automated smoke tests were added; full unittest discovery now passes 34 tests.
- **FROZEN:** API v1 read-only gate is satisfied. MCP v1 may now begin, constrained to read-only goal-oriented tools over API v1.
