# RackMarshal Investigator v1.1 Evaluation Gate

Status: **LIVE MCP PASS / MODEL-IN-THE-LOOP PENDING CREDENTIAL**
Date: 2026-09-29

## Production MCP acceptance

`evals/investigator_v1_1_live.json` is the permanent live-data acceptance suite for the 11-tool production MCP surface. It was run through a real MCP client against `http://127.0.0.1:8000/mcp` on CT 110.

Result: **18/18 cases passed**, using **30 production MCP calls** with zero evaluation failures.

Coverage includes RackMarshal health, current failures, current backup health, dynamically discovered open backup follow-up, long-running open incidents, recovered incidents, PVE legacy provenance, ZFS/HA/MOUNT lifecycle cases, fixed-window material-change compaction, recovery history, domain state, evidence dereferencing, deterministic repeated calls, invalid IDs, missing incidents, and invalid evidence-bundle limits.

The result artifact is `evals/results/investigator_v1_1_production_20260929.json`. It stores pass/fail/tool-call metadata only, not raw infrastructure evidence.

## Model-in-the-loop acceptance

`evals/investigator_v1_1_model.json` and `rackmarshal.agent.model_eval` define the Luna agent-quality gate. It scores required tool choice, typed evidence citation, recorded-vs-advisory separation, unsupported-cause uncertainty, recovery proof, provenance transparency, tool-call efficiency, and refusal of write/remediation authority.

This second gate is intentionally not marked passed yet: the temporary Responses-capable API key used for earlier proofs was revoked. CT 110 retains only the restricted Secure MCP Tunnel runtime credential.

UI/narrative development should begin after the model-in-the-loop gate passes, unless explicitly accepted as parallel work.


## First model run — 2026-09-29

The first GPT-6 Luna model-in-the-loop run completed 10 cases through Responses API -> Secure MCP Tunnel -> production 11-tool RackMarshal MCP. Result: **4/10 strict cases passed**. The run demonstrated correct safety behavior and generally accurate evidence-grounded answers, but exposed instruction/contract usability gaps: inconsistent use of both incident primitives, shortened evidence references, insufficient explicit Recorded/Advisory separation in one case, and one over-investigation case. No unsupported recovery or write action was claimed.

This is a useful failed product gate, not a platform failure. Investigator instructions were tightened to require the timeline + evidence-bundle pair for known incidents, canonical typed evidence IDs, explicit incident IDs, cause-vs-trigger distinction, clear Recorded/Advisory separation, and minimal sufficient tool use. A fresh model run is required before UI/narrative promotion.
