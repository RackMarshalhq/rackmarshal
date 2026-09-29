# RackMarshal MCP Architecture

Status: **DESIGN BASELINE**
Date: 2026-09-29

## Principle

MCP tools SHALL represent user goals, not mirror database tables or expose raw SQL.

The MCP server SHALL consume the public RackMarshal API or an equivalent stable service layer. It SHALL NOT read private SQLite tables directly.

## Phase 1: read-only tools

- `rackmarshal_get_health`
- `rackmarshal_get_status`
- `rackmarshal_list_incidents`
- `rackmarshal_get_incident`
- `rackmarshal_get_recent_changes`
- `rackmarshal_get_domain_status`
- `rackmarshal_get_backup_status`
- `rackmarshal_get_evidence`
- `rackmarshal_get_recovery_history`
- `rackmarshal_explain_state`

## Tool response requirements

Every tool response SHALL preserve provenance, observed time, authority level, source identifiers, and uncertainty where applicable.

MCP v1 is read-only. No infrastructure mutation tools are permitted in the first release.
