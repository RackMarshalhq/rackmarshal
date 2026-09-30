# RackMarshal Agent Security Model

Status: **DESIGN BASELINE**
Date: 2026-09-29

## Default posture

All external agent capabilities are deny-by-default. Read authority and action authority are separate grants.

## Capability classes

- **C0 READ** — inspect health, status, incidents, observations, evidence, and recovery history.
- **C1 OBSERVE** — request a fresh collection, verification, or other non-mutating diagnostic operation.
- **C2 REVERSIBLE** — request a bounded, reversible operational action.
- **C3 INFRASTRUCTURE CHANGE** — alter configuration, services, storage, networking, or monitored resources.
- **C4 HIGH-RISK** — operations that can remove data, resources, or protections and therefore require the strongest safeguards.

## Policy decisions

Each capability is evaluated as one of:

- `ALLOW`
- `ALLOW_WITH_AUDIT`
- `REQUIRE_APPROVAL`
- `DENY`

MCP v1 exposes C0 only.

## Audit requirements

For future C1-C4 requests, RackMarshal SHALL record requester identity, agent/runtime identity when available, capability, parameters, policy decision, approval identity if applicable, execution result, timestamps, and independent verification outcome.

## Secrets

Agent-facing interfaces SHALL return the minimum data needed for the task. Credentials, tokens, raw secrets, and private configuration values are never evidence payloads.
