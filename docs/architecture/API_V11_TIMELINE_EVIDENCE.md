# RackMarshal 1.1A — Timeline and Evidence Bundle Implementation Proof

Status: **VERIFIED — API/service gate passed; MCP expansion still gated**
Date: 2026-09-29

## Implemented surfaces

- `GET /v1/incidents/{incident_id}/timeline`
- `GET /v1/incidents/{incident_id}/evidence-bundle`

Both surfaces are deterministic, read-only, incident-scoped views over existing ledgers. No database migration was required.

## Production-data proof

The current implementation was exercised through a real `ThreadingHTTPServer` on isolated loopback port 19111 in CT 110 against `/var/lib/rackmarshal/state.db`.

- 82 real incidents were checked across BACKUP, PVE, MOUNT, HA, and ZFS.
- Hardware currently has 0 production incidents/events; hardware direct-event linkage is covered by automated fixture tests.
- Every real incident returned HTTP 200 for both timeline and evidence-bundle.
- Recovered incidents always contained `INCIDENT_RECOVERED`; open incidents never did.
- PVE used `LEGACY_RESOURCE_TIME_CORRELATION`; all other populated production domains used `DIRECT_EVENT_IDS`.
- 220 timeline evidence references were dereferenced successfully with zero failures.
- No returned timeline or bundle contained `payload_json`.
- Representative compact bundle sizes were approximately 4.7–7.9 KB; the largest bundle among the 82 incidents was 7,907 bytes.
- BACKUP:29 produced 2 timeline items and 1 compact material-change run despite its long repeated-abnormal history.

## Runtime boundary proof

The updated service code was installed in the RackMarshal MCP integration environment, but no new MCP tools were registered. Protocol discovery still advertises exactly the original 9 read-only tools.

## Test gate

The full suite passes 64 tests with `ResourceWarning` enabled and tracemalloc active, with zero ResourceWarnings.
