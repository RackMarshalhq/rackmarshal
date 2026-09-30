# RackMarshal Core Principles

Status: **FROZEN ARCHITECTURE BASELINE**
Date: 2026-09-29

## Non-negotiable principles

1. **Core independence** — RackMarshal SHALL provide complete monitoring, incident tracking, evidence retention, and recovery verification without any AI provider.
2. **Evidence authority** — AI output SHALL NOT become authoritative operational state unless validated by deterministic RackMarshal observation or explicit human input.
3. **Recovery authority** — Agents MAY recommend or initiate authorized recovery actions; RackMarshal determines whether recovery actually occurred.
4. **Least privilege** — Agent and API capabilities SHALL be deny-by-default and scoped to the minimum required authority.
5. **Auditability** — Every agent-requested action and every approval decision SHALL create durable, attributable evidence.
6. **Provider independence** — Public API and MCP contracts SHALL not depend on one model vendor, model family, or agent runtime.
7. **Local-first operation** — Core state, incidents, evidence, and policy remain local by default.
8. **Stable contracts** — External clients consume versioned APIs or MCP tools, never RackMarshal's private database schema.
9. **Human agency** — Potentially consequential infrastructure actions require policy-defined approval unless explicitly delegated.
10. **Fail-safe behavior** — Loss of AI, Internet access, or an agent runtime SHALL NOT prevent RackMarshal Core from monitoring or verifying recovery.

## Architectural rule

**AI consumes RackMarshal truth. AI does not define RackMarshal truth.**
