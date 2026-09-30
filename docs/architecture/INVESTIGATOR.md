# RackMarshal Investigator v1

Status: **BEHAVIOR CONTRACT IMPLEMENTED**
Date: 2026-09-29

The first RackMarshal agent behavior is a read-only operational investigator. It is not an autonomous operator.

It consumes only the nine VERIFIED MCP v1 tools. It may summarize and correlate RackMarshal evidence, but its synthesis is ADVISORY. It cannot create authoritative observations, invent severity, declare recovery without RackMarshal recovery evidence, mutate infrastructure, execute commands, or acknowledge/close incidents.

Initial investigation goals are current failures, a known incident, recovery verification, overnight changes, backup health, and single-domain investigation. The deterministic RackMarshal Core remains the authority for operational state.
