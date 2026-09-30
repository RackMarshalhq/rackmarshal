# RackMarshal MCP Architecture

Status: **MCP V1 TOOL SURFACE FROZEN / IMPLEMENTATION STARTED**
Date: 2026-09-29

## Principle

MCP tools SHALL represent user goals, not mirror database tables or expose raw SQL.

The MCP server SHALL consume the public RackMarshal API or an equivalent stable service layer. It SHALL NOT read private SQLite tables directly.

## Phase 1: read-only tools

- `get_health`
- `get_status`
- `list_incidents`
- `get_incident`
- `get_recent_changes`
- `get_domain_status`
- `get_backup_status`
- `get_evidence`
- `get_recovery_history`

## Tool response requirements

Every tool response SHALL preserve provenance, observed time, authority level, source identifiers, and uncertainty where applicable.

MCP v1 is read-only. No infrastructure mutation tools are permitted in the first release.

## Selection and safety contract

These nine tools are deliberately goal-oriented rather than a REST mirror. `explain_state` is deferred: explanation is an agent/skill responsibility over authoritative tool results, not a RackMarshal evidence-producing tool. Every v1 tool is annotated read-only, non-destructive, and closed-world. The MCP layer consumes API v1/service contracts and does not query SQLite directly.

The first implementation uses the official Python MCP SDK as an optional dependency and Streamable HTTP transport. Authentication/authorization and deployment exposure must be designed before any non-loopback/public deployment.


## SDK compatibility gate — 2026-09-29

RackMarshal MCP v1 is implemented against the official Python MCP SDK v1 compatibility line and SHALL declare `mcp>=1.28,<2`. The official SDK v2 line is a breaking redesign (`FastMCP` -> `MCPServer`) and SHALL NOT be adopted implicitly. Migration to SDK v2 requires a separate reviewed change and full protocol/security re-verification.
