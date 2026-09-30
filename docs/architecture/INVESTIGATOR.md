# RackMarshal Investigator v1

Status: **BEHAVIOR CONTRACT IMPLEMENTED**
Date: 2026-09-29

The first RackMarshal agent behavior is a read-only operational investigator. It is not an autonomous operator.

It consumes only the nine VERIFIED MCP v1 tools. It may summarize and correlate RackMarshal evidence, but its synthesis is ADVISORY. It cannot create authoritative observations, invent severity, declare recovery without RackMarshal recovery evidence, mutate infrastructure, execute commands, or acknowledge/close incidents.

Initial investigation goals are current failures, a known incident, recovery verification, overnight changes, backup health, and single-domain investigation. The deterministic RackMarshal Core remains the authority for operational state.


## Packaged agent artifact — 2026-09-29

The portable Investigator is packaged at `skills/rackmarshal-investigator/SKILL.md`, with repository agent guidance in `AGENTS.md` and plugin metadata in `.codex-plugin/plugin.json`. `.mcp.json` supplies the local development MCP target. The local target is intentionally loopback-only and is not a ChatGPT deployment endpoint.

For hosted ChatGPT, RackMarshal remains private and SHALL use Secure MCP Tunnel or another explicitly approved authenticated private connection rather than opening the MCP listener to the public Internet.
