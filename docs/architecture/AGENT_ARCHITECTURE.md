# RackMarshal Agent Architecture

Status: **DESIGN BASELINE**
Date: 2026-09-29

## Purpose

RackMarshal is the operational truth layer between infrastructure, humans, and autonomous agents.

Agents sit above deterministic RackMarshal Core. They may investigate, summarize, correlate, recommend, and—under explicit policy—request actions. They do not own authoritative infrastructure state.

## Layers

1. **Infrastructure** — Proxmox, ZFS, PBS/backups, Home Assistant, hardware, mounts, and future domains.
2. **RackMarshal Core** — observations, events, incidents, cycle health, evidence, notifications, recovery verification.
3. **RackMarshal API** — stable, versioned, provider-neutral external contract.
4. **RackMarshal MCP Server** — goal-oriented tools mapped to API capabilities.
5. **Agent runtimes** — ChatGPT, Codex, OpenAI Agents SDK/API, and compatible third-party runtimes.
6. **Humans and policy** — approval, delegation, ownership, and accountability.

## First agent role

The first RackMarshal-native agent SHALL be an **investigative operations agent**, not an autonomous remediation agent.

It gathers evidence, correlates change history, explains incidents, proposes checks, and recommends next actions. Any action authority is introduced later under the security model.
