# RackMarshal Architecture Roadmap

Status: **ACTIVE ROADMAP**
Date: 2026-09-29

## Current baseline

RackMarshal 1.0.0 is the stable public release. A six-domain 1.1 production candidate has already been qualified and migrated in controlled testing. The agent roadmap is additive to the existing 1.1 line.

## Sequence

### 1.1 — Complete current six-domain evolution
Preserve qualified domain/runtime work, delivery fixes, and production migration evidence. Do not destabilize this work to add AI features.

### 1.2 — Public API v1
Introduce a stable, read-only `/v1` contract above core state while preserving legacy `/health` and `/status`.

### 1.3 — Read-only MCP server
Expose goal-oriented RackMarshal tools backed by API v1. No direct SQLite access and no mutation tools.

### 1.4 — Agent-ready provenance
Standardize authority labels, evidence references, recovery history, pagination, and machine-readable change/event contracts.

### 1.5 — Investigative agent
Add a provider-neutral investigative operations agent, initially focused on evidence gathering, explanation, correlation, and recommendations.

### 2.0 — Controlled actions
Introduce capability classes, policy evaluation, approvals, and audited action requests.

### 2.1 — Agent audit ledger
Persist agent sessions, tool calls, requested actions, approvals, results, and independent recovery verification.

### 2.x — Multi-agent operations
Only after single-agent investigation and controlled actions are proven. Domain-specialized agents remain optional.
