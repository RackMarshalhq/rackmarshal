# RackMarshal Source of Truth

Date: 2026-09-29
Status: **AUTHORITATIVE PROJECT SOT**

## VERIFIED

- RackMarshal 1.0.0 is the stable public release.
- RackMarshal Core records durable operational state locally in SQLite.
- Current operational domains include PVE, ZFS, backup, Home Assistant, hardware, and mounts.
- The existing status service exposes local `/health` and `/status` endpoints.
- The current status API is read-only.
- AI explanation data already present in status output is advisory and non-authoritative.
- A six-domain RackMarshal 1.1 production candidate has been qualified under the existing gate documents.

## FROZEN ARCHITECTURE DECISIONS

- RackMarshal Core remains fully usable without AI.
- AI consumes RackMarshal truth; AI does not define RackMarshal truth.
- External integrations use stable API/MCP contracts, not private SQLite schema.
- API v1 begins read-only.
- MCP v1 begins read-only.
- Recovery is authoritative only after independent RackMarshal observation.
- Agent access is deny-by-default and capability-scoped.
- Provider independence is a product requirement.
- Consequential actions require policy-defined authority and audit evidence.

## ACTIVE DEVELOPMENT DIRECTION

The first-class post-1.1 development track is: public API v1 → read-only MCP → provenance/agent contract → investigative agent → controlled actions → agent audit ledger.

## IMPLEMENTATION GATE

No MCP implementation or autonomous-action implementation is authorized by this architecture freeze alone. The next implementation gate is API v1 schema review against the current RackMarshal data model, followed by read-only API implementation and contract tests. Existing RackMarshal 1.1 work remains independent and must not be destabilized by the agent track.


## API V1 SCHEMA REVIEW — 2026-09-29

- **VERIFIED:** The proposed read-only v1 surface can be normalized over the current six domain ledgers without changing their authoritative schemas.
- **FROZEN:** Public observation, event, and incident IDs are domain-qualified because local numeric IDs are not globally unique.
- **FROZEN:** API v1 does not invent severity where a domain ledger does not record it; unavailable severity is `null`/`UNKNOWN`.
- **FROZEN:** Recoveries are a normalized view over recovered incidents and their `recovered_observation_id`; no duplicate recovery authority is introduced.
- **FROZEN:** Raw collector payloads are not default public responses and require sanitization when exposed as typed evidence.
- **NEXT:** Implement the read-only service/adapters and contract tests. MCP remains gated until API v1 passes those tests.


## API V1 IMPLEMENTATION — 2026-09-29

- **VERIFIED:** Read-only API v1 service/adapters are implemented in `rackmarshal/api/v1.py` and routed through the existing status API server without changing legacy `/health` or `/status`.
- **VERIFIED:** v1 implements health, status, domains, incidents, observations, events/changes, evidence, recoveries, and backup status surfaces.
- **VERIFIED:** Domain-qualified public IDs, nullable severity, recovery evidence, opaque pagination, and raw-payload redaction are enforced by contract tests.
- **VERIFIED:** Full unittest discovery passes: 30 tests, including 7 API v1 contract tests and all 23 pre-existing tests.
- **FROZEN:** API v1 remains read-only; MCP is still not implemented.
- **NEXT:** Exercise v1 against a fresh-host/real RackMarshal database, add HTTP-level endpoint smoke tests, then decide whether the API gate is strong enough to begin MCP v1.


## API V1 REAL-DATA / HTTP PROOF — 2026-09-29

- **VERIFIED:** API v1 was run through the real `ThreadingHTTPServer` on isolated loopback port 19110 inside CT 110 against `/var/lib/rackmarshal/state.db` (~108 MB), without replacing or restarting the production listener on 9110.
- **VERIFIED:** Legacy `/health` and `/status` remained compatible; real `/status` and `/v1/status` agreed on `PROBLEM` with 2 open incidents at proof time.
- **VERIFIED:** All v1 read surfaces returned HTTP 200 against accumulated real data: health, status, six domains, incidents, observations, events, changes, recoveries, evidence, and backup status.
- **VERIFIED:** Real-data checks passed for domain-qualified IDs, nullable severity, incident detail, typed recovery/incident evidence, payload redaction, invalid numeric IDs, invalid cursors, unknown domains, domain filtering, and cursor traversal.
- **VERIFIED:** Four HTTP-level automated smoke tests were added; full unittest discovery now passes 34 tests.
- **FROZEN:** API v1 read-only gate is satisfied. MCP v1 may now begin, constrained to read-only goal-oriented tools over API v1.


## SQLITE RESOURCE CLEANUP — 2026-09-29

- **VERIFIED:** API v1 HTTP handler now explicitly closes each SQLite connection; transaction context management is no longer mistaken for connection lifetime management.
- **VERIFIED:** Notification/delivery tests explicitly close their in-memory SQLite connections.
- **VERIFIED:** Test-owned temporary directories/files now have explicit cleanup.
- **VERIFIED:** Full suite passes 34 tests under `PYTHONWARNINGS=always::ResourceWarning` with tracemalloc enabled and produces zero `ResourceWarning` messages.


## MCP V1 READ-ONLY TOOL SURFACE — 2026-09-29

- **FROZEN:** MCP v1 contains exactly nine goal-oriented tools: `get_health`, `get_status`, `list_incidents`, `get_incident`, `get_recent_changes`, `get_domain_status`, `get_backup_status`, `get_evidence`, and `get_recovery_history`.
- **FROZEN:** `explain_state` is not an MCP v1 tool; explanation belongs in the agent/skill layer and must remain distinguishable from RackMarshal evidence.
- **VERIFIED:** The tool service is implemented over API v1/service contracts only; it does not access SQLite directly.
- **VERIFIED:** Five MCP tool-service tests pass, including exact-surface, stable-ID, filtering, deterministic-status, and invalid-ID behavior.
- **NEXT:** Install the optional official MCP Python SDK in an isolated development environment, inspect the advertised schemas/annotations with MCP Inspector or SDK client tests, then exercise all nine tools against real RackMarshal data before deployment.


## MCP V1 PROTOCOL / SECURITY PROOF — 2026-09-29

- **VERIFIED:** Official MCP Python SDK v1.30.0 was installed only in isolated temporary environments; RackMarshal production dependencies were not changed.
- **VERIFIED:** The actual RackMarshal Streamable HTTP MCP server negotiated protocol `2025-11-25` with an official MCP client against CT 110's real RackMarshal database.
- **VERIFIED:** The server advertises exactly nine approved read-only tools: health, status, incident list/detail, recent changes, domain status, backup status, evidence, and recovery history.
- **VERIFIED:** All nine tools were invoked successfully through the MCP protocol against real accumulated data.
- **VERIFIED:** Every tool advertises `readOnlyHint=true`, `destructiveHint=false`, and `openWorldHint=false`; the server exposes zero resources and zero prompts.
- **VERIFIED:** Returned evidence contained no raw `payload_json` and no credential/secret-key field names from the audit denylist.
- **VERIFIED:** MCP argument schemas now explicitly type `limit` as integer; the initial protocol inspection caught and corrected the missing annotations before freeze.
- **FROZEN:** RackMarshal MCP v1 pins the official SDK compatibility line to `mcp>=1.28,<2`. SDK v2 is a breaking redesign and requires an explicit future migration/re-verification rather than an automatic dependency upgrade.
- **NEXT:** Add the first read-only RackMarshal Investigator skill/agent behavior over these nine tools. No infrastructure mutation authority is permitted.


## INVESTIGATOR V1 — 2026-09-29

- **VERIFIED:** The first RackMarshal agent behavior contract is implemented as a read-only Investigator over exactly the nine VERIFIED MCP v1 tools.
- **VERIFIED:** Contract tests enforce that the Investigator has no tool outside the verified MCP surface and that incident/recovery investigations require evidence/recovery-history tools.
- **FROZEN:** Investigator synthesis is ADVISORY. RackMarshal Core remains authoritative for observations, incidents, and recovery.
- **FROZEN:** Investigator v1 has no infrastructure mutation, shell, SQL, incident-closing, or acknowledgement authority.
- **NEXT:** Package the Investigator as a provider-neutral skill/instruction artifact and connect it to ChatGPT/Codex through the verified MCP server; retain human control and read-only authority.


## INVESTIGATOR PACKAGING — 2026-09-29

- **VERIFIED:** Investigator instructions are packaged as a portable skill at `skills/rackmarshal-investigator/SKILL.md`.
- **VERIFIED:** Repository-level `AGENTS.md` requires Codex/agents to use RackMarshal MCP rather than bypassing the evidence boundary during Investigator work.
- **VERIFIED:** Plugin manifest and local `.mcp.json` package the skill plus MCP connection for a Codex-capable environment.
- **EXPECTED:** Hosted ChatGPT connection requires a reachable private MCP path. RackMarshal will use Secure MCP Tunnel rather than exposing CT 110's MCP listener publicly.
- **BLOCKED:** This current ChatGPT Plus surface cannot directly attach the new local RackMarshal MCP from inside this conversation; the account/UI connection step requires developer-mode/plugin support and a reachable MCP endpoint.

## END-TO-END AGENT PROOF — 2026-09-29

- **VERIFIED:** OpenAI Responses API using GPT-6 Luna successfully reached the private RackMarshal MCP server through Secure MCP Tunnel `RackMarshal Home` and completed a real evidence-grounded investigation against CT 110's production RackMarshal database.
- **VERIFIED:** Response `resp_0f55cf71b7a19e54006abc696d4e8c87d2ba505f4f81d16bbc` completed successfully and used only the approved read-only RackMarshal MCP surface.
- **VERIFIED:** Tool sequence included `get_recent_changes`, `list_incidents`, and `get_recovery_history`; all MCP calls completed successfully through the tunnel.
- **VERIFIED:** The Investigator separated recorded facts from advisory interpretation and cited RackMarshal incident/evidence IDs. It correctly reported persistent stale phone-backup incidents `BACKUP:26` and `BACKUP:29`, and did not claim a cause unsupported by evidence.
- **VERIFIED:** Secure MCP Tunnel remains outbound-only; RackMarshal MCP remains bound to `127.0.0.1:8000`.
- **OBSERVED:** The successful proof consumed 48,673 total model tokens because `get_recent_changes` returned repeated polling-cycle change records. This is an efficiency issue, not a correctness failure; add investigation-oriented deduplication/bounding before routine agent use.


## INVESTIGATION CHANGE COMPACTION — 2026-09-29

- **VERIFIED:** `get_recent_changes` now uses a material-change view rather than returning every polling-cycle event. Raw `/v1/events` remains unchanged for forensic access.
- **VERIFIED:** Repeated observations of the same condition are collapsed per resource while preserving first/latest event IDs, first/latest evidence refs, first/latest values, timestamps, and repeat count. A transition away and back remains a separate material change.
- **VERIFIED:** `get_recent_changes` now supports explicit UTC `since` and `until` bounds.
- **VERIFIED:** Real production data for 2026-09-29 18:00Z through 2026-09-30 02:00Z collapsed 170 raw BACKUP events into 2 material change runs (168 repetitive polling events removed from the agent payload) while preserving the Olivia and Preston stale-backup evidence chain.
- **VERIFIED:** Full suite passes 48 tests with zero `ResourceWarning` messages.
