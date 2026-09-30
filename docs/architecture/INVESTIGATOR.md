# RackMarshal Investigator v1

Status: **VERIFIED / FROZEN — READ-ONLY V1**
Date: 2026-09-29

The first RackMarshal agent behavior is a read-only operational investigator. It is not an autonomous operator.

It consumes only the nine VERIFIED MCP v1 tools. It may summarize and correlate RackMarshal evidence, but its synthesis is ADVISORY. It cannot create authoritative observations, invent severity, declare recovery without RackMarshal recovery evidence, mutate infrastructure, execute commands, or acknowledge/close incidents.

Initial investigation goals are current failures, a known incident, recovery verification, overnight changes, backup health, and single-domain investigation. The deterministic RackMarshal Core remains the authority for operational state.


## Packaged agent artifact — 2026-09-29

The portable Investigator is packaged at `skills/rackmarshal-investigator/SKILL.md`, with repository agent guidance in `AGENTS.md` and plugin metadata in `.codex-plugin/plugin.json`. `.mcp.json` supplies the local development MCP target. The local target is intentionally loopback-only and is not a ChatGPT deployment endpoint.

For hosted ChatGPT, RackMarshal remains private and SHALL use Secure MCP Tunnel or another explicitly approved authenticated private connection rather than opening the MCP listener to the public Internet.

## Investigator v1 freeze — 2026-09-29

Investigator v1 is frozen around the nine read-only MCP tools, evidence/advisory authority boundary, Secure MCP Tunnel deployment, material-change compaction, permanent evaluation suite, and optional OpenAI Responses API edge client. RackMarshal Core remains fully usable without AI. Future write/action capability requires a separately versioned authority contract and does not modify Investigator v1.

## Investigator 1.1 read-only expansion — 2026-09-29

RackMarshal 1.1 promotes two additional goal-oriented read-only tools after isolated protocol/security proof: `get_incident_timeline` and `get_incident_evidence_bundle`. The Investigator now prefers these for known-incident work because RackMarshal deterministically assembles lifecycle and evidence context before advisory interpretation. The original nine tools remain available and behaviorally intact. The authority boundary is unchanged: all 11 tools are read-only; RackMarshal Core remains authoritative and fully usable without AI.
