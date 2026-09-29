# RackMarshal API Architecture

Status: **DESIGN BASELINE**
Date: 2026-09-29

## Goal

Provide a stable, versioned interface between RackMarshal Core and all external clients, including MCP servers, agents, UI clients, integrations, and automation.

The existing local `/health` and `/status` endpoints remain supported. API v1 is additive and SHALL preserve current core behavior.

## Rules

- API clients SHALL NOT depend on SQLite schema.
- API v1 begins read-only.
- Responses SHALL include schema/version metadata where appropriate.
- Timestamps SHALL use UTC ISO-8601.
- IDs SHALL remain durable within a RackMarshal installation.
- Unknown data SHALL be explicit rather than guessed.
- AI-generated explanation fields SHALL be labeled advisory/non-authoritative.
- Pagination SHALL be used for unbounded collections.
- Error responses SHALL be structured and machine-readable.

## Initial endpoint surface

- `GET /v1/health`
- `GET /v1/status`
- `GET /v1/domains`
- `GET /v1/domains/{domain}`
- `GET /v1/incidents`
- `GET /v1/incidents/{id}`
- `GET /v1/observations`
- `GET /v1/events`
- `GET /v1/changes`
- `GET /v1/evidence/{id}`
- `GET /v1/recoveries`
- `GET /v1/backups/status`
