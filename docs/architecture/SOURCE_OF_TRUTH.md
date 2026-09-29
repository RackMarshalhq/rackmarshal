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
