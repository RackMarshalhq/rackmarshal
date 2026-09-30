# RackMarshal MCP v1.1 — Incident Investigation Tool Contract

Status: **FROZEN IMPLEMENTATION CONTRACT**
Date: 2026-09-29

## Purpose

Add exactly two goal-oriented, read-only investigation tools over the proven API v1.1 incident surfaces. They do not create a generic REST mirror and do not change RackMarshal's authority boundary.

## Tool: `get_incident_timeline`

Use when an agent has a canonical incident ID and needs the ordered lifecycle: opening, material transitions, latest abnormal evidence, and independently observed recovery when present.

Input schema:
- `incident_id`: string, required. Canonical RackMarshal ID such as `BACKUP:29`.

Output is the API envelope from `GET /v1/incidents/{incident_id}/timeline`. The tool MUST preserve provenance and MUST NOT infer cause, severity, or recovery.

## Tool: `get_incident_evidence_bundle`

Use when an agent has a canonical incident ID and needs one compact evidence package for investigation, reducing repeated evidence calls.

Input schema:
- `incident_id`: string, required. Canonical RackMarshal ID such as `BACKUP:29`.
- `limit`: integer, optional, default 50, range 1–50. Bounds material-change runs only.

## Shared authority and safety contract

- Both tools are read-only and non-destructive.
- MCP annotations MUST advertise `readOnlyHint=true`, `destructiveHint=false`, and `openWorldHint=false`.
- Neither tool accepts arbitrary SQL, paths, evidence refs, domain tables, URLs, commands, or free-form query expressions.
- Neither tool exposes raw collector `payload_json`, credentials, secrets, or unrestricted host data.
- Invalid canonical IDs MUST become tool errors rather than fallback searches.
- Missing incidents MUST become tool errors rather than empty/synthesized investigations.
- Returned evidence and lifecycle state remain RackMarshal deterministic state; interpretation belongs to the Investigator.

## Public surface gate

The public MCP surface MUST remain at 9 tools until protocol tests prove both additions against the real RackMarshal database. Promotion is all-or-nothing: after the gate passes, discovery MUST advertise exactly 11 tools, with these two names added and no other capability.

## Protocol acceptance

Before promotion, an isolated candidate MCP server MUST prove:
1. exact names, descriptions, input schemas, and read-only annotations;
2. successful calls for open and recovered real incidents;
3. PVE legacy provenance remains explicit;
4. evidence bundles remain bounded and sanitized;
5. invalid IDs and invalid limits fail safely;
6. no write/destructive/unintended tools are advertised;
7. the existing nine tools remain behaviorally intact.
