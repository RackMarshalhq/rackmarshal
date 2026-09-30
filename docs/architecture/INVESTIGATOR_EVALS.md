# RackMarshal Investigator v1 Evaluation Suite

Status: **FROZEN CONTRACT**
Date: 2026-09-29

The permanent evaluation set is `evals/investigator_v1.json`. It covers ten representative investigation goals: overnight failures, current failures, recoveries, incident analysis, precursor changes, backup health, RackMarshal health, incident evidence, recovery proof, and PVE-domain history.

Each case declares the minimum RackMarshal tools required to answer responsibly. Automated tests reject unknown/non-RackMarshal capabilities and verify that the declared plans stay inside the nine-tool read-only MCP surface.

## Evaluation principles

- Evidence-producing questions must use RackMarshal tools rather than unsupported model memory.
- Recovery claims require RackMarshal recovery evidence.
- Causal language remains advisory unless directly recorded as evidence.
- Stable incident/evidence IDs should be retained in user-facing explanations when they materially support a conclusion.
- Time-bounded questions should resolve explicit UTC boundaries and use `since`/`until`.
- Repetitive polling should be consumed through material-change compaction rather than raw forensic-event pagination.
- Shell, filesystem, SQL, infrastructure mutation, and incident mutation are prohibited.

## Live proof

The 2026-09-29 production-data compaction proof reduced 170 BACKUP polling events in the representative overnight window to 2 material-change runs while retaining first/latest evidence and values. The original OpenAI/Luna end-to-end proof remains VERIFIED. A post-compaction model-token remeasurement requires a temporary Responses-capable API credential and is deliberately not stored as a RackMarshal runtime secret.
