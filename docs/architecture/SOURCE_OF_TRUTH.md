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


## INVESTIGATOR V1 FREEZE / EVALS — 2026-09-29

- **VERIFIED / FROZEN:** RackMarshal Investigator v1 is a read-only evidence consumer over the nine-tool MCP v1 surface. RackMarshal Core remains authoritative and fully usable without AI.
- **VERIFIED / FROZEN:** Secure MCP Tunnel provides the private OpenAI connection; the MCP listener remains loopback-only.
- **VERIFIED / FROZEN:** `get_recent_changes` uses material-change compaction with explicit `since`/`until` bounds while `/v1/events` remains the forensic event stream.
- **VERIFIED:** Permanent Investigator evaluation contract contains 10 representative investigation cases and rejects capabilities outside the nine-tool read-only surface.
- **VERIFIED:** An optional `rackmarshal-investigate` OpenAI Responses API edge client is packaged with GPT-6 Luna as its default model and the exact nine-tool allowlist; it requires runtime credentials and does not make RackMarshal Core depend on AI.
- **SECURITY:** The temporary full-access Responses API key was revoked by the operator and its CT 110 credential file was removed. No broad Responses credential is retained by RackMarshal.
- **PENDING MEASUREMENT:** The post-compaction external Luna token count has not been remeasured because the temporary Responses credential was deliberately revoked. The production data-path proof shows 170 raw overnight BACKUP events collapsing to 2 material-change runs.


## RACKMARSHAL 1.1A CONTRACT FREEZE — 2026-09-29

- **FROZEN:** RackMarshal 1.1A begins with deterministic Incident Timeline and Incident Evidence Bundle contracts.
- **FROZEN:** Proposed endpoints are `GET /v1/incidents/{incident_id}/timeline` and `GET /v1/incidents/{incident_id}/evidence-bundle`.
- **VERIFIED:** Current ledgers support both features without a schema migration. ZFS, BACKUP, HA, HARDWARE, and MOUNT incidents carry direct event linkage (`opened_event_id`, `last_event_id`). PVE is a legacy exception and must use explicit `LEGACY_RESOURCE_TIME_CORRELATION` provenance based on resource identity, lifecycle timestamps, and authoritative observation IDs.
- **FROZEN:** Timeline/evidence construction is deterministic and read-only; no AI causation or severity inference enters the canonical data.
- **FROZEN:** Recovery appears only when authoritative `recovered_observation_id` and `recovered_at` exist.
- **FROZEN:** Evidence bundles remain incident-bounded, compact material changes, and never expose raw `payload_json` or secrets.
- **NEXT:** Implement API v1.1 timeline/evidence-bundle service functions and contract tests against real ledgers; MCP expansion remains gated until those API contracts pass.


## RACKMARSHAL 1.1A API IMPLEMENTATION / REAL-DATA PROOF — 2026-09-29

- **VERIFIED:** Incident Timeline and Incident Evidence Bundle service functions are implemented with routes `GET /v1/incidents/{incident_id}/timeline` and `GET /v1/incidents/{incident_id}/evidence-bundle`.
- **VERIFIED:** No database migration was required. Existing authoritative incident/event/observation ledgers are sufficient.
- **VERIFIED:** Isolated real-HTTP proof on CT 110 against `/var/lib/rackmarshal/state.db` checked all 82 current production incidents across BACKUP, PVE, MOUNT, HA, and ZFS with zero lifecycle/provenance failures. Hardware currently has no production incidents/events and is covered by direct-linkage fixture tests.
- **VERIFIED:** 220 timeline evidence references dereferenced successfully; no timeline or evidence bundle exposed raw `payload_json`.
- **VERIFIED:** Recovery is present only for incidents with authoritative recovery fields; open incidents never receive synthetic recovery.
- **VERIFIED:** PVE is explicitly marked `LEGACY_RESOURCE_TIME_CORRELATION`; populated non-PVE domains use `DIRECT_EVENT_IDS`.
- **VERIFIED:** Evidence bundles are compact and bounded (maximum 50 material-change runs); representative production bundles were ~4.7–7.9 KB.
- **VERIFIED:** Full suite passes 64 tests with zero `ResourceWarning` messages.
- **GATE HELD:** Updated service code is installed in the MCP integration runtime, but MCP protocol discovery still advertises exactly the original 9 read-only tools. `get_incident_timeline` and `get_incident_evidence_bundle` are NOT exposed yet.
- **NEXT:** Design/freeze the two goal-oriented MCP tool contracts over these now-proven API/service surfaces, then protocol-test them before expanding the public MCP surface from 9 to 11 tools.


## RACKMARSHAL 1.1A MCP CONTRACT FREEZE — 2026-09-29

- **FROZEN:** The next MCP expansion contains exactly two goal-oriented tools: `get_incident_timeline` and `get_incident_evidence_bundle`.
- **FROZEN:** `get_incident_timeline` accepts only required canonical `incident_id`. `get_incident_evidence_bundle` accepts required canonical `incident_id` plus optional integer `limit` (default 50; range 1–50).
- **FROZEN:** Both tools remain read-only/non-destructive/closed-world and expose only the proven API v1.1 deterministic incident surfaces. No SQL, filesystem paths, commands, URLs, arbitrary query expressions, raw payloads, or write authority are accepted/exposed.
- **FROZEN:** Invalid IDs/limits and missing incidents fail as tool errors; no fallback search or synthesized incident data is permitted.
- **GATE HELD:** Public MCP remains exactly 9 tools. The two additions are not registered until an isolated candidate MCP server passes protocol discovery/schema/annotation/call/error/sanitization tests against the real RackMarshal database.
- **PROMOTION TARGET:** After that proof, public MCP discovery must expose exactly 11 tools and no additional capability.


## RACKMARSHAL 1.1A MCP 9→11 PROMOTION — 2026-09-29

- **VERIFIED:** An isolated candidate MCP server ran on CT 110 loopback `127.0.0.1:18001` against the real RackMarshal database and advertised exactly 11 tools: the original nine plus `get_incident_timeline` and `get_incident_evidence_bundle`.
- **VERIFIED:** Both new tools advertised the frozen descriptions and minimal schemas. Their schemas explicitly set `additionalProperties=false`; all 11 tools advertised `readOnlyHint=true`, `destructiveHint=false`, and `openWorldHint=false`.
- **VERIFIED:** Real MCP-client calls succeeded for open `BACKUP:29`, recovered `BACKUP:33`, and legacy-linkage `PVE:35`. Open incidents did not synthesize recovery; recovered incidents returned recorded recovery; PVE retained `LEGACY_RESOURCE_TIME_CORRELATION`.
- **VERIFIED:** Evidence/timeline responses contained no raw `payload_json` or detected secret markers. Evidence bundles remained bounded.
- **VERIFIED:** Nine deliberate boundary attacks were rejected: malformed/numeric IDs, invalid domain, missing incident, non-integer/high/zero limits, and arbitrary SQL/path/URL arguments. Extra arguments are explicitly forbidden rather than silently ignored.
- **VERIFIED:** Existing representative tools (`get_health`, `get_status`, `get_incident`, `get_recent_changes`) continued to succeed on the candidate server. Candidate promotion gate result: `PASS` with zero failures.
- **PROMOTED:** Production RackMarshal MCP on CT 110 was upgraded from 9 to exactly 11 read-only tools. The same promotion acceptance suite passed against production with zero failures.
- **VERIFIED:** Secure MCP Tunnel remained `ready`; production MCP remained `active`. The isolated candidate listener was stopped and its temporary files removed after promotion.
- **VERIFIED:** RackMarshal Investigator allowlist/evals now include the two promoted tools and prefer timeline/evidence-bundle workflows for known incidents.


## INVESTIGATOR V1.1 LIVE EVALUATION — 2026-09-29

- **VERIFIED / PASS:** Permanent production-MCP acceptance suite `evals/investigator_v1_1_live.json` ran through the actual 11-tool MCP server on CT 110 and passed 18/18 cases using 30 real MCP calls with zero failures.
- **VERIFIED:** Coverage includes dynamic current failures/backup state, open and recovered incident follow-up, PVE legacy provenance, ZFS/HA/MOUNT lifecycle cases, material-change compaction, recovery history, evidence round-trip, determinism, sanitization, invalid IDs, missing incidents, and bundle-limit enforcement.
- **VERIFIED:** Result metadata is archived as `evals/results/investigator_v1_1_production_20260929.json`; raw infrastructure evidence is not stored in the artifact.
- **IMPLEMENTED / PENDING RUN:** Model-in-the-loop suite `evals/investigator_v1_1_model.json` and evaluator `rackmarshal.agent.model_eval` score Luna tool choice, typed evidence citation, recovery proof, provenance, uncertainty/cause boundaries, fact-vs-advisory separation, efficiency, and read-only authority behavior.
- **SECURITY:** Model-in-the-loop gate is not falsely marked passed. The prior temporary Responses-capable key was revoked; CT 110 retains only the restricted Secure MCP Tunnel runtime credential. A temporary Responses-capable key is required to execute this final agent-quality gate.
- **GATE:** Incident UI/narrative work begins after the model-in-the-loop gate passes, unless the operator explicitly chooses parallel development.


## INVESTIGATOR V1.1 MODEL GATE — FIRST RUN 2026-09-29

- **FAILED / USEFUL:** GPT-6 Luna completed the real Responses API -> Secure MCP Tunnel -> production 11-tool RackMarshal MCP evaluation. Strict result: 4/10 cases passed.
- **VERIFIED:** The model correctly respected read-only authority, did not claim remediation, did not invent recovery, and generally stayed evidence-grounded.
- **FAILED:** Tool-choice/answer-contract consistency was insufficient: some known-incident questions used only one of timeline/bundle; some answers shortened typed evidence IDs; one answer lacked explicit Recorded/Advisory separation; the overnight case exceeded the efficiency threshold.
- **CORRECTIVE CHANGE:** Investigator instructions now require timeline + evidence bundle for known incidents, exact typed evidence refs, explicit incident IDs, trigger-vs-root-cause distinction, clear fact/advisory separation, and minimal sufficient tool use.
- **SECURITY VERIFIED:** `/etc/rackmarshal/model-eval.env` was deleted immediately after the run. The temporary key itself must still be revoked in the OpenAI project by the operator.
- **GATE REMAINS CLOSED:** A fresh model-in-the-loop run must pass before incident UI/narrative work begins under the current gate.


## INVESTIGATOR V1.1 MODEL GATE — FINAL PASS 2026-09-29

- **VERIFIED / PASS:** GPT-6 Luna passed 10/10 model-in-the-loop cases through the real Responses API -> Secure MCP Tunnel -> production 11-tool RackMarshal MCP path.
- **VERIFIED:** Final run used 22 MCP calls and 54,590 total model tokens across the 10-case suite.
- **VERIFIED:** The successful suite covers current failures, overnight investigation, open-incident explanation, recovery proof, PVE legacy provenance, MOUNT lifecycle, unsupported-cause boundaries, evidence-bundle use, read-only action refusal, and backup health.
- **VERIFIED:** Investigator instructions now require canonical typed evidence IDs, explicit incident IDs, timeline + evidence bundle for known incidents, explicit Recorded facts / Advisory interpretation where appropriate, cause-vs-trigger separation, and bounded/minimal investigation behavior.
- **VERIFIED:** Evaluator retries transient HTTP 429 responses rather than misclassifying provider throttling as an agent-quality failure.
- **SECURITY VERIFIED:** `/etc/rackmarshal/model-eval.env` was deleted immediately after the passing run. The operator must revoke the temporary OpenAI API key itself after this proof.
- **GATE OPEN:** Incident narrative/UI work may now proceed.


## INCIDENT NARRATIVE / DETAIL PAGE — FIRST SLICE 2026-09-29

- **FROZEN:** Deterministic incident summary contract lives at `contracts/ui-v1.1/INCIDENT_SUMMARY_PAGE.md`. The summary/page use RackMarshal ledger facts only and do not require or invoke AI.
- **IMPLEMENTED:** `GET /v1/incidents/{incident_id}/summary` returns deterministic headline/opened/latest/recovery/cause statements, canonical evidence refs, provenance, and `authority=DERIVED`.
- **IMPLEMENTED:** `GET /incidents/{incident_id}` renders a local read-only incident detail page with state, deterministic summary, ordered timeline, evidence links, and linkage provenance. It exposes no remediation/acknowledge/close/restart controls.
- **SECURITY VERIFIED:** All ledger-derived HTML is escaped; pages expose no raw `payload_json`. Response headers include `no-store`, `nosniff`, and a restrictive Content-Security-Policy.
- **VERIFIED:** Isolated HTTP proof passed for open direct-linkage `BACKUP:29`, recovered direct-linkage `BACKUP:33`, and recovered PVE legacy-linkage `PVE:35`.
- **PROMOTED / VERIFIED:** Production RackMarshal status service on CT 110 serves the new summary API and incident page on port 9110. Production smoke tests passed for all three representative incidents.
- **NEXT:** Add an incident index/list page and refine deterministic narrative semantics before adding richer cross-incident correlation UI.


## INCIDENT INDEX / DASHBOARD — 2026-09-30

- **IMPLEMENTED:** `GET /` and `GET /incidents` render the deterministic, read-only human incident dashboard.
- **OPEN FIRST:** The dashboard separates all currently OPEN incidents from recent recovery history and orders each section by its authoritative lifecycle timestamp.
- **VISIBLE FIELDS:** Incident ID, domain, resource type/key/display name, state, and opened/recovered timestamp are shown with links to the existing incident detail pages.
- **DEGRADED-SCHEMA SAFE:** The dashboard aggregates only incident ledger tables present in the database, without changing core API behavior.
- **SECURITY:** Ledger-derived text is HTML-escaped; no raw `payload_json` is rendered; the existing no-store/nosniff/restrictive-CSP headers apply. There are no write/remediation controls and no AI invocation.
- **REAL-DATA PROOF:** Isolated CT 110 proof rendered the current production ledger, including BACKUP, PVE, and MOUNT open incidents plus recent recoveries.
- **PRODUCTION VERIFIED:** `/`, `/incidents`, `/incidents/BACKUP:29`, and `/incidents/PVE:43` returned HTTP 200 on production port 9110. Representative current links `BACKUP:38`, `PVE:43`, and `MOUNT:9` were present.
- **CURRENT SNAPSHOT AT PROOF:** 33 OPEN incidents were present in the ledger. This is a time-specific observed snapshot, not a frozen system invariant.


## INCIDENT NARRATIVE REFINEMENT — 2026-09-30

- **IMPLEMENTED / PROMOTED:** Dashboard now explains recorded OPEN vs historical
  RECOVERED state, groups open counts by domain, shows resource display/type/key
  and incident type, exact lifecycle timestamps, and recorded occurrence counts.
  Detail pages add an at-a-glance lifecycle, readable timeline labels and repeat
  counts, navigation back to incidents, canonical JSON/evidence links, and
  plain-language direct/legacy linkage and authority explanations.
- **BOUNDARIES PRESERVED:** DERIVED presentation uses normalized ledger facts.
  No model calls, inferred severity/cause/recovery, remediation controls, raw
  payloads, public ingress, or workspace changes. HTML escaping and existing
  no-store/nosniff/restrictive-CSP headers were verified.
- **CORRECTNESS FIX:** Dashboard traverses incident pagination instead of silently
  taking only the newest 200 records per domain. Missing domain ledgers and
  missing fields are labeled; absent counts/times are never inferred.
- **TESTED:** 107/107 tests pass on staging Python 3.13 and CT 110 Python 3.11,
  with ResourceWarnings enabled and zero ResourceWarnings. Nine additional
  narrative tests cover >200-row pagination/count/recovery ordering, unavailable
  domains, missing fields, state boundaries, direct/legacy provenance, evidence
  links, escaping, absent controls, and timeline repeat-count semantics.
- **HTTP PROVEN:** Candidate loopback 9112, production loopback 9110, and production
  LAN 192.168.50.110:9110 each pass 35 read-only HTTP checks. Representative
  incidents: BACKUP:38 OPEN direct, BACKUP:39 RECOVERED direct, PVE:43 OPEN legacy,
  MOUNT:9 OPEN direct. Every cited evidence link resolves to its canonical ID.
  Metadata-only proof artifacts are in evals/results/incident-narrative-*-
  20260930.json; scripts/prove-incident-narrative.py reruns the acceptance check.
- **DEPLOYMENT:** Exact tested api/v1.py and three UI files were copied to the
  existing CT 110 package and verified by SHA-256. Only the status service was
  restarted. Prior files are retained in
  /var/lib/rackmarshal/deployment-backups/narrative-20260930 for rollback.
  Status/MCP/tunnel services remain active; tunnel /healthz and /readyz return
  HTTP 200 live/ready. The isolated candidate listener was stopped after proof.
- **OPERATIONAL SNAPSHOT:** At 2026-09-30 10:01 UTC (06:01 America/New_York),
  recorded overall status was PROBLEM with 33 open incidents: BACKUP 4, PVE 8,
  MOUNT 21; 20 recent recoveries shown. This is a dated ledger snapshot, not a
  system invariant or a claim of current host health.
- **EXISTING OPERATIONAL LIMITATION:** Before promotion, systemd reported failed
  domain cycle units for HA/HARDWARE/MOUNT/PVE/ZFS and self-watch. Their timers
  were active; latest recorded ledger state may differ from live cycle success.
  No domain cycle was restarted, no incident was changed, and no remediation
  was performed in this presentation task. UI acceptance is not a full
  infrastructure-health gate.
- **NEXT STEP PREPARED ONLY:** Business workspace connection sequence, exact
  verified Investigator policy, 11-tool inventory, and workspace acceptance
  prompts are documented in CHATGPT_BUSINESS_CONNECTION_PREPARATION.md.
  Existing historical Investigator gates do not establish that new workspace
  integration has been completed or verified.


## CHATGPT BUSINESS CONNECTION READINESS — 2026-09-30

- **LOCAL READY:** Status, MCP, and Secure MCP Tunnel services are active; tunnel health is `live` and readiness is `ready`.
- **DOCTOR VERIFIED:** A non-conflicting ephemeral-listener `tunnel-client doctor` run returned `result: ok` with the MCP target reachable.
- **BUSINESS PATH VERIFIED AGAINST CURRENT OPENAI GUIDANCE:** Business Admins/Owners can create custom MCP apps in developer mode on ChatGPT web. Private RackMarshal MCP should remain behind Secure MCP Tunnel.
- **NO PUBLIC INGRESS REQUIRED:** Do not expose port 8000 or port 9110 publicly for ChatGPT integration.
- **EXTERNAL ADMIN GATE:** Associate the existing tunnel with the intended Business workspace and create the RackMarshal Investigator custom app from the authenticated workspace admin UI. This cannot be certified from the RackMarshal host alone.
- **ACCEPTANCE GATE REMAINS:** After app creation, scan exactly the 11 read-only tools and run the documented workspace acceptance prompts before publishing or widening access.


## CYCLE RELIABILITY AND RECOVERY PROVENANCE — 2026-09-30

- **USER AUTHORIZED / PROMOTED:** Bounded engineering repairs restore scheduled
  domain processing and self-watch without changing incident schemas, baselines,
  observation authority, security policy, credentials, or API/MCP write scope.
- **DELIVERY:** All six domain runners and self-watch pass ordinary string argv
  to delivery. The unused legacy --explainer flag is optional; explanations
  remain cached/advisory. Queue-empty regression execution covers all seven.
- **LOCKS:** HA, ZFS, and HARDWARE lock under the configured state database parent,
  already writable under the existing systemd sandbox. ProtectSystem remains
  strict; no additional filesystem permission was granted.
- **MOUNT CONFIGURATION:** Collector honors the selected RackMarshal config and
  configured PVE_NODE, preserves explicit environment overrides, URL-encodes the
  node path, and fails before an empty-node request. Existing API TLS/credential
  settings remain unchanged.
- **PROCESSORS:** HA defaults to its packaged comparator; ordered, bounded catch-up
  processes pending observations through the new observation without skipping
  lifecycle records. Hardware invokes its module argv directly, eliminating a
  Path(list) error. Real disposable-ledger regressions execute both processors.
- **AUTHORITY CORRECTION:** last_event_id may point to recovery. Timeline and
  evidence bundle now pair last abnormal evidence with the authoritative last
  abnormal observation, never borrowing a later healthy event. If an abnormal
  event is absent, observation-only evidence remains explicit. Repeated runs
  remain visible even when their endpoints coincide with lifecycle events.
- **PUBLICATION:** Replaced site/person names in test fixtures with fictional
  identifiers. Publication gate now passes its actual privacy scan, full tests,
  compilation, and fresh-database staging smoke (30 manifests, 17 safe CLIs).
- **TESTED:** 121 discovery tests pass on staging Python 3.13 and CT 110 Python
  3.11 with ResourceWarnings enabled and zero ResourceWarnings. Skill-creator
  quick_validate.py reports Skill is valid for the Investigator skill.
- **REAL PRODUCTION PROOF:** At 13:35 UTC, all six domain observations were fresh
  per MCP; all six domain cycles and self-watch had success/exit 0. Status, MCP,
  and tunnel were active; tunnel health/readiness returned live/ready HTTP 200.
  At 13:41 UTC, production LAN HTTP passed 37 checks and real MCP Investigator
  evaluation passed 18/18. Proof artifacts are metadata-only under evals/results.
- **RECOVERY AUTHORITY:** Independent MOUNT observation MOUNT:3685 at
  2026-09-30T13:23:54.546Z checked 23 resources successfully and the normal
  processor recorded 21 recoveries. The configured existing notification
  pipeline delivered 21 recovery notifications, with zero delivery failures.
  No incident rows were manually closed or rewritten. MOUNT:9 now records
  abnormal event MOUNT:2337 / observation MOUNT:3684 separately from recovery
  event MOUNT:2358 / observation MOUNT:3685.
- **DATED SNAPSHOT:** Recorded status remains PROBLEM with 12 OPEN incidents:
  BACKUP 4 and PVE 8. HA, ZFS, HARDWARE, MOUNT record zero OPEN incidents. Successful
  collectors do not imply these remaining infrastructure incidents recovered.
- **ROLLBACK:** Each promoted source file was copied with SHA-256 verification;
  pre-change files are under /var/lib/rackmarshal/deployment-backups in
  cycle-delivery-20260930, health-lock-mount-20260930,
  health-processors-20260930, health-ha-backlog-20260930,
  health-lifecycle-20260930, health-lifecycle-mcp-20260930, and
  health-repeat-counts-20260930, and health-lock-cleanup-20260930. Restore the relevant package files in reverse
  deployment order; restart status/MCP only for API rollback. Collector-produced
  evidence/recoveries remain durable history and are never undone by code rollback.
- **BUSINESS PREPARATION:** Investigator skill now has validated YAML metadata,
  exact verified v1.1 policy, compact workflows, and an explicit operational vs
  engineering scope. Local plugin version is 0.1.1. A separate skills-only
  preparation bundle is available; no cloud MCP binding/app identifier is
  invented. Existing loopback .mcp.json is local-only. Workspace association,
  registration, permissions, and publication remain unperformed pending the
  user's explicit integration request and authenticated admin context.


## REPRODUCIBLE CODE PROMOTION — 2026-09-30

- **BOUNDED DELIVERABLE COMPLETE:** scripts/promote-package-files.py provides prepare, plan, apply, and rollback for qualified Python-only patches to existing status/MCP installations. It reuses the committed HTTP narrative proof, Investigator live-evaluation runner, and suite; the release installer remains unchanged.
- **PINNED SOURCE:** Preparation requires a full commit SHA and reads committed blobs, never working-tree content. Manifest hashes cover selected source and acceptance assets. Plan independently discovers both package roots using isolated interpreter execution, rejects unsafe paths, and compares hashes. Unchanged source is a no-op without backups/restarts.
- **TRANSACTION:** Exclusive host lock, original bytes/modes/ownership, journal, timer/service quiescence excluding tunnel, per-file atomic replacement, affected bytecode invalidation, SHA-256 checks in both packages, bounded readiness and acceptance, then prior active timers/long-running services restored. No schemas, dependencies, credentials, service policy, or authoritative incidents are modified. In-flight oneshot jobs can be interrupted and resume by their normal timers.
- **ROLLBACK:** Copy, checksum, readiness, or acceptance failures restore original code and runtime. Conflicting later edits/corrupt backups are refused; failures are recorded and workload is not deliberately resumed without recovery. Explicit rollback supports an interrupted transaction. Code rollback never erases already recorded observations/recoveries/notifications.
- **TESTS:** 134 tests pass on staging Python 3.13; CT 110 Python 3.11 runs 134 with 133 passing and the single staging-only Git preparation test skipped because Git is absent. Zero ResourceWarnings. Publication/privacy/compile/fresh-database gate PASS. Thirteen additional tests cover real temporary installations and failure paths; production needs no newly installed dependency.
- **READ-ONLY PRODUCTION QUALIFICATION:** Prepared api/v1.py from 28534ba293a4aece9b67410c797aaae03a2d1008; both installed package hashes match (zero proposed changes). Read-only systemd snapshot covers 26 units and readiness passes. Pinned scripts run directly from the prepared bundle pass 37 HTTP checks and 18/18 actual MCP cases at approximately 11:21 AM America/New_York.
- **LIMITATION EXPLICIT:** Production stop/start and file mutation are not exercised by this task. Disposable regressions cover those paths; use the tool at the next authorized, independently qualified patch promotion and preserve its transaction/acceptance receipt. No unchanged production source was redeployed and no workspace changes were made.
- **OPERATOR DOCS:** docs/architecture/REPRODUCIBLE_CODE_PROMOTION.md covers scope, command sequence, qualification, maintenance effects, recovery, and evidence retention. Metadata-only proof artifacts are evals/results/package-promotion-{qualification,http,mcp}-20260930.json.
- **NEXT CHECKPOINT:** Commit this procedure and pause the bounded-task heartbeat. Continue next with domain freshness/cycle-success presentation or read-only review of the remaining incident evidence. The Business connection remains prepared but unregistered.


## COLLECTION COVERAGE UI — 2026-09-30

- **QUALIFIED CANDIDATE:** Dashboard and incident detail show latest domain observation time, canonical observation evidence, observation freshness using the existing self-watch policy, the freshness evaluation time, and exact current-unit recorded cycle results. These are separate from incident lifecycle state.
- **RECORDING GAP EXPLICIT:** Current rackmarshal-domain@*.service unit names have no cycle-health ledger rows at proof time. Older unit results are displayed only as explicitly labeled historical records, with exact unit names, recorded result/success/failure times, and cumulative recorded failure counts. No historical success is promoted to current health, and no missing cycle result is inferred.
- **BOUNDED / SANITIZED:** Metadata-only observation SELECTs use newest recorded IDs and do not fetch payload_json. Current-unit state, stored timestamps, and unknown/missing fields are labeled. Detail_json and cached AI explanations are not rendered; no live host/service probes, model calls, remediation controls, or writes are added. Incident/API/MCP authority contracts remain unchanged.
- **TESTS:** 139 tests pass on staging Python 3.13; target Python 3.11 runs 139 with 138 passing and one staging-only Git preparation test skipped. Zero ResourceWarnings; publication gate PASS. Five new narrative regressions cover configured policy, missing metadata, current/legacy unit separation, failure versus historical recovery, and escaping/no raw detail.
- **CANDIDATE HTTP:** Isolated CT listener on loopback 9112 passes 45 checks against real production data, including six current domain observations and typed evidence links. All six observations are fresh at approximately 11:39 AM America/New_York; all exact current-unit cycle results are NOT_RECORDED. Candidate listener and temporary config were removed after proof.
- **PROMOTION GATE:** Use the pinned source commit through scripts/promote-package-files.py for api/status.py, ui/dashboard.py, and ui/incidents.py in both installed packages. Promote only if runtime readiness, pinned HTTP acceptance, and existing MCP evaluation pass. Save transaction receipt and final proof, then update this section with actual production outcome.
