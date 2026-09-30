# RackMarshal Source of Truth

Date: 2026-09-30
Status: **AUTHORITATIVE PROJECT SOT**

## CURRENT VERIFIED CHECKPOINT — 2026-09-30

This summary supersedes earlier dated next-step and incident-count snapshots below. Operational counts describe the saved production proof at 17:10–17:11 UTC, not a perpetual system guarantee. The remaining sections preserve the evidence and development history.

- **PRODUCTION:** Read-only API, MCP Investigator and deterministic incident dashboard/detail pages are implemented and live on CT 110. Status, MCP and tunnel services are active. Dashboard: http://192.168.50.110:9110/incidents.
- **PVE POLICY:** All eight retained LXC containers 117–124 have accepted VERIFIED baseline entries: 117–123 expected stopped, 124 expected running. Existing 20 entries preserved; total baseline 28. Source observation:PVE:11340 and explicit user approval recorded. Operator administration remains separate from read-only Investigator access.
- **RECORDED RECOVERIES:** PVE:36–PVE:43 recovered through normal collection/processing at 17:05:44.344970 UTC, supported by observation:PVE:11345. PVE status OK, zero open PVE incidents. PBS weekly evidence visibility repaired earlier; BACKUP:38 recovered from observation:BACKUP:11333. No manual incident closure or guest state change.
- **REMAINING OPEN:** Three phone BACKUP incidents; overall status PROBLEM. Michael backup planned tonight September 30; Olivia and Preston October 5. Plans do not establish recovery or waive the seven-day backup policy. Normal recorded observations must prove subsequent recovery.
- **QUALIFICATION:** Staging 173 test executions PASS; CT Python 3.11 172 pass/one existing Git-only skip; zero ResourceWarnings. Production HTTP 47 checks PASS, MCP acceptance 18/18 PASS, LAN dashboard/detail sanitization and evidence links PASS. Consistent private baseline backup retained at /var/lib/rackmarshal/deployment-backups/pve-baseline-3edeeage.
- **SOURCE CHECKPOINT:** Baseline operator implementation 26cb00c209427bc0d86c9366917322e418fd0786; accepted production proof/docs a7f762a84242892b8cf6b9d3d2d9d71ceb8c283e. CT API/MCP package remains the qualified 5d78a4d6e2cd5411d70fdd198df76ac790b414b4 deployment; standalone PBS observer source 5ad27c66b72bd80c9ed3187500ba00938d008876. Baseline adoption required no package redeployment.
- **NEXT:** Observe phone backup recovery through ordinary evidence. ChatGPT Business connection checklist is prepared; workspace registration, association, permissions and credentials remain unchanged and require explicit setup instructions. UI/Investigator stay local-first, sanitized, read-only and non-AI-dependent, with no remediation controls.


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

## INITIAL IMPLEMENTATION GATE — HISTORICAL 2026-09-29

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

- **IMPLEMENTED / PROMOTED:** Dashboard and incident detail show latest domain observation time, canonical observation evidence, observation freshness using the existing self-watch policy, the freshness evaluation time, and exact current-unit recorded cycle results. These are separate from incident lifecycle state.
- **RECORDING GAP EXPLICIT:** Current rackmarshal-domain@*.service unit names have no cycle-health ledger rows at proof time. Older unit results are displayed only as explicitly labeled historical records, with exact unit names, recorded result/success/failure times, and cumulative recorded failure counts. No historical success is promoted to current health, and no missing cycle result is inferred.
- **BOUNDED / SANITIZED:** Metadata-only observation SELECTs use newest recorded IDs and do not fetch payload_json. Current-unit state, stored timestamps, and unknown/missing fields are labeled. Detail_json and cached AI explanations are not rendered; no live host/service probes, model calls, remediation controls, or writes are added. Incident/API/MCP authority contracts remain unchanged.
- **TESTS:** 139 tests pass on staging Python 3.13; target Python 3.11 runs 139 with 138 passing and one staging-only Git preparation test skipped. Zero ResourceWarnings; publication gate PASS. Five new narrative regressions cover configured policy, missing metadata, current/legacy unit separation, failure versus historical recovery, and escaping/no raw detail.
- **CANDIDATE HTTP:** Isolated CT listener on loopback 9112 passes 45 checks against real production data, including six current domain observations and typed evidence links. All six observations are fresh at approximately 11:39 AM America/New_York; all exact current-unit cycle results are NOT_RECORDED. Candidate listener and temporary config were removed after proof.
- **PRODUCTION ACCEPTED:** Source d219b51b6d5ac62fc062a9a0b2e45d914b44f41e was promoted through the new pinned procedure. Three changed UI-serving modules plus the shared ui/__init__.py and ui/narrative.py dependencies were selected. Eight files changed across the installations; unchanged bytes were skipped. Transaction /var/lib/rackmarshal/deployment-backups/d219b51b6d5a-9hvaylv0 records ACCEPTED after SHA-256 verification, readiness, 45 HTTP checks, and 18/18 MCP cases. All 12 previously active timers were restored; status, MCP, and tunnel are active. LAN dashboard and MOUNT:9 detail returned HTTP 200 with expected security headers and collection coverage at 11:45 AM America/New_York. Database/incident state was not manually altered and the tunnel was not reconfigured. Metadata proof artifacts are evals/results/collection-coverage-{deployment,production-http,production-mcp,lan}-20260930.json.

- **NEXT RECORDING GAP:** Instrument current cycle units to publish durable cycle_health results through the existing recorder, without treating observation freshness or historical unit rows as current execution evidence. This UI task exposes that gap and does not silently repair or infer its ledger contents.


## CURRENT-UNIT CYCLE RECORDING — 2026-09-30

- **QUALIFIED CANDIDATE:** Existing cycle_health recorder supports final systemd metadata. Packaged drop-ins cover rackmarshal-domain@.service and an already-existing rackmarshal-self-watch.service. Exact %n keys, invocation provenance, completion timestamps, retained failure history, conservative success/exited/0 classification, and legacy CLI compatibility are tested. No schema or authority contract changes.
- **BOUNDARIES:** Only cycle_health is written. No manual incident/observation edits or remediation. Hook inherits current user/sandbox and adds no writable paths. Recorder errors remain logged and do not replace the main result. Installer packages nested drop-ins and does not create/enable optional self-watch.
- **QUALIFICATION:** Staging publication gate PASS: 146 tests, zero ResourceWarnings. Target Python 3.11: 145 pass, one Git-only staging test skipped, zero ResourceWarnings. Disposable CT systemd fixture passes failure/exit 7, recovery retaining failure_count=1, and logged recorder error with main success preserved. Fixture ledger/unit removed; metadata-only proof evals/results/cycle-recording-systemd-20260930.json. docs/architecture/CYCLE_RESULT_RECORDING.md documents semantics and separate code/unit rollback.
- **PRODUCTION ACCEPTED:** Recorder source 8a11750e171624fd53c43d7ec2abe3265790acf8 promoted to both status/MCP installations (two changed files), SHA-256 checked, through transaction /var/lib/rackmarshal/deployment-backups/8a11750e1716-0nf995wj. Pinned HTTP/MCP acceptance passed. The two pinned drop-ins were installed separately with verified hashes and untouched base-unit hashes; unit backup/receipt /var/lib/rackmarshal/deployment-backups/cycle-hooks-22a6tbuy. All seven prior active domain/self-watch timers restored. Status, MCP and tunnel active.
- **REAL RECORDING PROOF:** Normal domain and self-watch runs at 16:04:41–16:04:50 UTC (12:04 PM America/New_York) recorded SUCCESS/exited 0 under all seven exact current service names, read through /status. No test rows were inserted into production. At 16:05 UTC, HTTP passed 45 checks showing six current-unit SUCCESS results and fresh observations; real MCP passed 18/18. LAN dashboard and MOUNT:9 detail passed HTTP/security checks. Recorded incidents remain 12 OPEN: BACKUP 4, PVE 8; cycle completion does not assert incident recovery.
- **ROLLBACK RECEIPT:** First drop-in attempt completed real cycles but the deployment proof misread /status cycle_health as a list rather than its keyed map. It restored original drop-ins, reloaded units, and restored all seven timers; code and recorded history remained intact. The corrected proof also waits for activating/deactivating oneshots before mutation. Retry accepted. Both receipts retained; no runtime failure is hidden.
- **PACKAGING PROOF:** Actual installer bundle script ran against disposable inputs; both nested drop-ins are in its archive. Placeholder wheel was never installed. Production base units/configuration, privileges, credentials and workspace connections are unchanged.
- **EVIDENCE / CHECKPOINT:** Metadata-only cycle-recording-{systemd,bundle-fixture,code-deployment,unit-deployment,unit-rollback,production-http,production-mcp,lan}-20260930.json retained under evals/results. Durable current-name recording restored. Next useful work is bounded read-only evidence review of the remaining BACKUP/PVE incidents; Business connection remains prepared and unregistered.


## OPEN-INCIDENT REVIEW / BUSINESS CHECKLIST — 2026-09-30

- **READ-ONLY REVIEW COMPLETE:** Production MCP cohort at 16:11:40 UTC contains all 12 OPEN incidents: BACKUP:26, BACKUP:29, BACKUP:34, BACKUP:38 and PVE:36–PVE:43. Timelines/bundles for all 12 show no recovery evidence; pagination complete. Observation freshness is current, not a stale-collector explanation.
- **RECORDED CONDITIONS:** Three existing phone backup paths exceed 168-hour age policy (Michael 181.466 h, Preston 241.870 h, Olivia 275.541 h). BACKUP:38 records weekly_verification_task_not_found, unknown weekly status/age, and no proven weekly job failure or recovery. Separate host-backup verification success does not substitute for PBS weekly proof. Eight PVE NEW incidents cover LXC 117–124 absent from baseline; expected status unknown, seven stopped/one running. Qualification-style names suggest inventory review but do not authorize disposal or baseline edits.
- **CONFIRMED BOUNDED BUG:** _incident_events() filters event detection time by incident observation time, excluding the newest lagging PVE event from material compaction while latest_abnormal_evidence correctly resolves it by observation ID. Live cohort has 143 occurrences versus 142 compacted repeats. Existing in-memory fixture reproduces 2/latest event 8 versus 1/latest event 7 with ResourceWarnings as errors. No fix deployed, incident closed, or production DB bypassed. Next code deliverable: observation/lifecycle-bounded selection with resource identity, re-opened-lifecycle and detection-lag regressions, preserving legacy provenance.
- **ARTIFACTS:** docs/architecture/OPEN_INCIDENT_REVIEW_20260930.md gives every incident, typed evidence refs, recorded facts and ADVISORY actions. evals/results/open-incidents-review-20260930.json retains compact MCP audit/evidence; open-review-readiness-20260930.json verifies eleven read-only tools and health/freshness; open-review-pve-timestamp-fixture-20260930.json records reproduction. No redundant suite run or unchanged-code promotion was performed.
- **BUSINESS PREPARATION COMPLETE:** Rewritten CHATGPT_BUSINESS_CONNECTION_PREPARATION.md supplies current official flow, exact tool inventory, actual-ID/plugin binding steps, authority policy, nine workspace acceptance cases, scope/removal checkpoints and explicit pending gates. Local tunnel HTTP live/ready proof retained in business-readiness-20260930.json. Workspace identity, policy, association, registered ID and actual workspace acceptance remain unverified. No registration, permission grant, credential change, public exposure or publishing performed.


## PVE LIFECYCLE EVIDENCE COMPACTION — 2026-09-30

- **QUALIFIED FIX:** PVE material evidence now uses exact resource type/key, matching incident condition and inclusive opened/last-abnormal observation IDs. Detection time remains the recorded event timestamp but cannot omit the final observation's event. Recovery and re-opened lifecycles cannot leak into the prior abnormal run. Missing lifecycle IDs yield no inferred material history. Other domains retain their existing event-time selection. Correlated observation lookups also match resource type when available.
- **AUTHORITY:** No ledger/schema change, event/incident rewrite or live resource probe. Legacy PVE linkage remains LEGACY_RESOURCE_TIME_CORRELATION; authoritative latest-abnormal and separate recovery evidence retain their roles. Repeat counts describe recorded matching events, not independent outages. Resource identity/incident state are not automatically accepted or remediated.
- **CHECKS:** Five new regression cases cover detection lag, recovered/replacement condition, prior/later lifecycles, resource-type/condition collisions and absent bounds. Full publication gate: 161 test executions PASS, zero ResourceWarnings; target Python 3.11: 160 pass plus one Git-only skip, zero ResourceWarnings. Existing fixture-class imports cause new cases to execute in multiple discovery modules; these are five new cases, not fifteen distinct tests. Real CT candidate loopback HTTP passes 45 checks and all eight PVE bundles have 146 compacted repeats equal to their recorded occurrences, with identical latest event identities and OPEN state at 16:30 UTC. Candidate listener removed after proof. Metadata artifacts pve-compaction-candidate{-http,}-20260930.json.
- **PRODUCTION ACCEPTED:** Code 5d78a4d6e2cd5411d70fdd198df76ac790b414b4 promoted via pinned Python-only procedure to both installations, two changed files with SHA-256 verification. Transaction /var/lib/rackmarshal/deployment-backups/5d78a4d6e2cd-qz653zay is ACCEPTED with rollback originals retained. Pinned production HTTP passes 45/45 and MCP acceptance 18/18. Focused actual MCP proof at 16:32:40 UTC confirms all eight PVE incidents have matching latest material/event identities and 147 compacted repeats equal to recorded occurrences, OPEN state and unchanged legacy provenance. LAN dashboard/PVE:43 detail pass HTTP/security checks. All 12 prior active timers restored and verified active; status/MCP/tunnel active. Twelve incidents remain OPEN (BACKUP 4, PVE 8). No production ledger was manually edited, no schema/configuration/unit changes, no credential/workspace changes.
- **PROOF:** pve-compaction-{deployment,production-http,production-mcp,production-proof,lan}-20260930.json under evals/results. The earlier review's compaction defect is resolved; its dated incident/root-cause limitations remain applicable. Next bounded engineering investigation is PBS weekly task selection/evidence completeness, without implying a failed verification run or introducing Investigator host access.
- **OPERATOR PLAN:** User plans Michael phone backup tonight September 30 and Olivia/Preston backups October 5. This is an ADVISORY scheduling note, not observed backup success or an incident waiver. Seven-day policy and normal recorded-recovery requirement remain unchanged.


## PBS WEEKLY VERIFICATION TASK WINDOW — 2026-09-30

- **MCP TRIGGER:** BACKUP:38 still records weekly_verification_task_not_found at observation:BACKUP:11326/event:BACKUP:1614, with no recovery evidence. This establishes missing observer evidence, not a failed weekly verification job.
- **DEVELOPMENT DIAGNOSIS:** Existing host cache helper /usr/local/sbin/pbs-native-verify-cache queries the latest 100 unfiltered PBS tasks through existing QGA, then matches exact verificationjob + datastore/job worker_id. The 100 tasks contain no exact weekly job. Read-only 1000-task query finds configured weekly-homelab results at positions 133 and 178, both OK. Latest scheduled completion: 2026-09-27T08:36:59+00:00 (start 08:30 UTC). Job exists with sun 04:30 schedule, ignore-verified false. This is development/repair access, not added Investigator authority.
- **BOUNDED FIX:** Existing standalone helper is versioned under packaging/observers/pbs-native-verify-cache and changes only task-list limit 100 to supported maximum 1000. Exact type/worker ID match, result selection, cache permissions/path and service behavior preserved. No verification job is run or configuration changed. If no match appears within 1000 tasks the result remains unknown/not found; this is bounded history visibility, not exhaustive historical absence. CLI supports all/limit/output-format, not typefilter. Primary CLI documentation: https://pbs.proxmox.com/docs/proxmox-backup-manager/man1.html.
- **QUALIFICATION:** Five fixture regressions exercise the actual helper and embedded query: exact weekly result beyond 100, rejection of individual snapshot/other-job success, failed newest job versus older success, running newest job versus completed history, and execution error. Staging full publication gate 166 executions PASS, zero ResourceWarnings; target Python 3.11 executes 166 with 165 passing/one Git-only skip, zero ResourceWarnings. Engineering metadata receipt: evals/results/pbs-weekly-diagnosis-20260930.json.
- **PRODUCTION ACCEPTED:** Host helper source 5ad27c66b72bd80c9ed3187500ba00938d008876 deployed from the committed blob. Original SHA-256 and new SHA-256 checked; original bytes retained in /var/lib/homelab-monitor/pbs-cache-window-ie06au2w with receipt, file ownership/mode preserved, existing probe timer quiesced then restored. Normal helper execution found the actual latest weekly OK result (endtime 1790498219, age 80.169 h) with no probe errors. Existing unit/credentials and job schedule are unchanged; the standalone observer source is a packaging artifact, not newly installed by the CT release installer. CT package code remains the previously qualified PVE fix.
- **RECOVERY AUTHORITY:** Normal BACKUP collector/comparator/processor independently recorded recovery of BACKUP:38 at 2026-09-30T16:47:09.364907Z from observation:BACKUP:11333. Last abnormal evidence remains observation:BACKUP:11332; recovery evidence is observation-only, with no invented recovery event. Actual MCP timeline contains INCIDENT_RECOVERED and bundle state RECOVERED. No incident was manually closed, no success row injected, and no new verification job launched. Evidence visibility was repaired; the underlying successful job was already completed September 27.
- **FINAL PROOF:** Production HTTP passes 46 checks (additional recovered representative); real MCP Investigator acceptance 18/18. LAN dashboard/BACKUP:38 detail pass HTTP/security and show canonical recovery evidence. Status/MCP/tunnel, CT backup timer and host probe timer are active. Recorded OPEN count is now 11: BACKUP 3 (phone delays noted), PVE 8 (NEW inventory). Metadata receipts pbs-weekly-{before,diagnosis,deployment,production-proof,production-http,production-mcp,lan}-20260930.json under evals/results.
- **CHECKPOINT:** Missing weekly evidence resolved, without changing the eight-day native verification SLA or seven-day phone policy. The remaining PVE inventory decision requires intended-resource context; no cleanup/baseline edits performed. Business workspace registration/association/permissions remain unperformed. Observer history remains bounded at 1000 tasks, so future not-found results must not be called proof of a failed weekly job.


## USER-AUTHORIZED PVE BASELINE ADOPTION — 2026-09-30

- **AUTHORIZATION:** User explicitly requested “Keep them and create a new baseline” for the eight qualification LXC resources 117–124. This authorizes scoped operator baseline administration, not container disposal, guest state changes, manual incident closure or expansion of Investigator privileges.
- **PLAN:** Fresh read-only MCP PVE snapshot identifies observation:PVE:11340 at 16:58:32.889191 UTC, with eight OPEN NEW incidents. Operator plan reads that exact recorded snapshot and proposes eight insert-only VERIFIED entries: expected stopped for 117–123, running for 124; source observation and user approval note recorded. Existing 20 baseline entries preserved. No adoption or recovery claimed at this source checkpoint.
- **QUALIFICATION:** scripts/adopt-pve-baseline.py is an operator-only tool with root apply, explicit resources/pinned fresh observation, private consistent backup, transaction revalidation, atomic inserts, rejection of unknown/missing/duplicate resources and refusal to overwrite baseline rows. Seven fixture cases cover plan no-write, expected states/source/unselected preservation/private snapshot, missing scope, conflict preservation, duplicate scope, stale data and database-failure rollback. Publication gate 173 test executions PASS; target Python 3.11 172 pass/one Git-only skip, zero ResourceWarnings on both. docs/architecture/PVE_BASELINE_ADOPTION.md documents roles, execution and baseline-only rollback without erasing recorded history.
- **PRODUCTION APPLIED:** Source 26cb00c209427bc0d86c9366917322e418fd0786, pinned operator script SHA-256 d839d6d427246d3c7a95cd9e6e51393e9f9408e522821a37bc48956a266dddc8. At 17:05:43 UTC the PVE timer was quiesced and the insert-only transaction added eight VERIFIED entries, increasing baseline count 20 to 28. Private consistent backup and receipt retained at /var/lib/rackmarshal/deployment-backups/pve-baseline-3edeeage. Existing entries and guest states preserved. Timer restored; normal PVE service cycle completed. No schema, installed package, unit policy, credential or workspace change.
- **RECOVERY PROOF:** Independent production MCP bundles confirm PVE:36–PVE:43 RECOVERED at 2026-09-30T17:05:44.344970Z, all supported by observation:PVE:11345. Latest abnormal observation:PVE:11344 remains separate, occurrence count 153 retained, and LEGACY_RESOURCE_TIME_CORRELATION provenance remains explicit. No incident rows manually changed. This resolves NEW inventory conditions by adopting intended policy; it does not claim an underlying guest repair or independent outages. PVE is OK with zero open incidents; three BACKUP phone incidents remain OPEN.
- **ACCEPTANCE:** Production HTTP 47 checks PASS, Investigator MCP 18/18 PASS, LAN dashboard/detail security and canonical recovery links PASS. Status/MCP/tunnel services and PVE timer active. Subsequent normal observation:PVE:11348 remains fresh and its durable cycle result SUCCESS. Full test qualification above remains applicable; no unchanged-code redeployment or redundant suite run. Application, production-proof, production-http, production-mcp and LAN metadata saved as pve-baseline-*-20260930.json in evals/results.
- **CHECKPOINT:** Eight containers retained with accepted states (117–123 stopped; 124 running). Michael phone backup planned September 30 tonight, Olivia/Preston October 5; these plans are not recovery evidence or SLA waivers. Business connection preparation remains complete, with registration/association/permissions explicitly pending user setup instructions.


## BUSINESS CONNECTION SETUP INSPECTION — 2026-09-30

- **USER REQUEST:** Work on the Business connection after SoT update. Authenticated Chrome identifies RackMarshal Business; Plugins Add → Create MCP App exposes the Tunnel connection form. Exact admin role, tunnel workspace association and audience remain unverified. Security and login showed no Developer mode toggle; available form used without changing security settings.
- **PREPARED:** Existing rackmarshal-home tunnel identified from a scoped CT profile inspection without credential exposure. Name/description, existing tunnel ID and server No authentication selection reviewed in the draft. No additional OAuth credentials or public endpoint proposed. Draft dismissed before acknowledgment/Create.
- **PENDING:** Action-time confirmation for creating new read-only access through the existing private tunnel; required by Computer Use policy. No connection registered, no association or permission change, no credentials created, no public exposure. After authorized registration: inspect eleven tools and actual ID/audience, bind Investigator policy and perform workspace acceptance. Business checklist updated to latest 173-test/47-HTTP/18-MCP local qualification and recovered PVE/PBS examples.


## Business registration attempt and association prerequisite — 2026-09-30

User explicitly confirmed creation of RackMarshal Investigator through the
existing private tunnel for initial private testing. Two bounded Create attempts
in authenticated RackMarshal Business returned “Couldn't create MCP app. Try
again.” No successful connection ID or discovered tool inventory returned;
workspace acceptance remains pending. Do not report the connection as created.

Local /healthz and /readyz return HTTP 200 live/ready; MCP and tunnel services
active. No recent tunnel journal entries. Doctor confirms profile, tunnel ID,
control-plane key presence, MCP reachability and absence of OAuth metadata;
its health-listener failure is an expected bind conflict with the already
running production listener on 127.0.0.1:8080, not evidence that the live service
is down. Production service was not stopped or reconfigured for diagnostics.

Authenticated Platform Tunnels shows RackMarshal Home associated with Personal
organization and no ChatGPT workspace. Edit offers RackMarshal workspace
7a12a28c-ed93-4d70-be81-0a459c667e1a. Missing association is a verified unmet
prerequisite and likely cause; the generic registration error alone does not
prove the backend cause. Only that workspace is selected in an unsaved draft,
preserving Personal organization. Save has not been clicked. Specific user
confirmation is required to expand the existing tunnel association to this
workspace, then retry the already-authorized private connection registration.
No new tunnel, credential, public ingress, broader publication, or runtime
permissions are proposed. Association allows the target workspace to find/use
the tunnel subject to its existing controls; it does not certify operator-only
audience. Inspect actual audience and tool inventory after registration.


## BUSINESS CONNECTION REGISTERED — 2026-09-30

- **AUTHORIZED ASSOCIATION:** User explicitly confirmed saving the existing RackMarshal Home tunnel association with RackMarshal Business and retrying registration. Platform Save completed; table now shows RackMarshal workspace, preserving Personal organization and the existing tunnel identity. No new tunnel, credentials, runtime service changes or public ingress.
- **REGISTERED:** RackMarshal Investigator is installed and Connected at https://chatgpt.com/plugins/plugin_asdk_app_6abd4868c4e481919c3900f583f35322. Actual registered technical ID: plugin_asdk_app_6abd4868c4e481919c3900f583f35322. Cloud UI version 1.0.0 is distinct from repository skill plugin 0.1.1. This supersedes prior pending/failed registration checkpoints.
- **DISCOVERY VERIFIED:** Actual ChatGPT action dialog categorizes exactly eleven tools as Read: get_backup_status, get_domain_status, get_evidence, get_health, get_incident, get_incident_evidence_bundle, get_incident_timeline, get_recent_changes, get_recovery_history, get_status, list_incidents. No infrastructure write/shell/SQL tool.
- **BUSINESS SMOKE:** Fresh plugin-selected GPT-6.1 Sol Medium conversation RackMarshal Acceptance Test (https://chatgpt.com/c/6abd48d0-ee68-83ea-902d-7aee3d5c3523) shows Used RackMarshal Investigator and three call titles: Listing Open Incidents, Checking RackMarshal operational health, Assessing Domain States and Incidents. Completed response reports health OK/database readable, overall PROBLEM/three OPEN incidents BACKUP:34, BACKUP:29, BACKUP:26; generated_at timestamps 17:37:44 UTC, no additional incident page, PVE/ZFS/HA/HARDWARE/MOUNT OK. Recorded facts and ADVISORY interpretation separated; no recovery inferred or remediation performed. These values are the actual workspace response, not substituted local SDK output. Raw request/response expansion/export remains pending.
- **LIMITS/NEXT:** Registration and initial read connectivity verified, not the full Investigator experience. Cloud connection has no bundled skill yet. Capture supported registered-ID package binding, install reviewed Investigator policy, then run remaining fresh-conversation evidence/lifecycle/refusal cases and verify actual audience/admin action controls. Do not equate the workspace tunnel association with operator-only audience or broader publication. No separate broader sharing change performed. Metadata saved in evals/results/business-connection-registration-20260930.json.


## Business Investigator policy binding and acceptance — 2026-09-30

The existing registered app `asdk_app_6abd4868c4e481919c3900f583f35322` is now paired with private installed skill `6abd4bdd1b5081918e0475ff6678b873`. The web editor saved the verified v1.1 policy plus explicit existing-app binding and `agents/openai.yaml` MCP dependency. Canonical policy SHA-256: `e8771dd88bcee2fd0d2d7078325a8af6d26b6c10d81b1ddb68556dbb7d93be41`. The cloud developer app and private skill remain separate artifacts; the qualified combined package in `packaging/chatgpt-business` has not been installed as a combined cloud plugin.

Four fresh ChatGPT Work acceptance conversations explicitly selected the installed skill. They passed current OPEN inventory, phone/PBS/PVE lifecycle explanation, exact typed evidence references, recorded recovery/provenance, fact/advisory separation, metadata-only evidence limitations, bounded UTC summary with honest pagination limits, infrastructure/manual incident closure refusal, and unsupported-resource UNKNOWN behavior. The UTC summary explicitly disclosed additional incident/recovery pages; it is not an exhaustive inventory. The refusal case showed no tool usage. Raw tool arguments/results were not exported; proof is rendered answers and visible tool trace titles. Implicit skill activation is not yet qualified.

Proof receipt: `evals/results/business-policy-acceptance-20260930.json`. Full staging suite: 173 tests PASS with ResourceWarnings treated as errors, zero ResourceWarnings. Package JSON/YAML and canonical policy inclusion validated. No production code changed or redeployed. No workspace publication, credentials, permissions, or tunnel changes occurred. Production remains read-only with three phone backup incidents OPEN at acceptance time; only future recorded observations may establish recovery.

Next useful step: normal private operational use with the skill explicitly selected; optionally qualify implicit activation and a complete paginated inventory when required. Broader workspace distribution still requires explicit instruction.


## PRIVATE OPERATIONAL USE CHECKPOINT — 2026-09-30

- **USER FEEDBACK:** User reports deliberately asking about unmonitored systems, receiving coverage limitations and future-expansion planning without invented monitoring, and being very happy with the Investigator. This is user-reported acceptance, not exported tool-trace proof of those additional conversations.
- **SCOPE:** Continue normal private operational use with the Investigator explicitly selected. Downloads, network, and storage usage monitoring remain deferred; no collector, incident policy, permission expansion, controlled action, or broader workspace distribution is authorized by this checkpoint.
- **RECORDED MCP SNAPSHOT:** get_status generated_at 2026-09-30T19:01:37.810957Z reports overall PROBLEM, three BACKUP incidents, and PVE/ZFS/HA/HARDWARE/MOUNT OK. list_incidents(state=OPEN, limit=50) generated_at 2026-09-30T19:01:38.560967Z returns BACKUP:34 (michael), BACKUP:29 (preston), BACKUP:26 (olivia), total 3, next_cursor null. All three last abnormal conditions reference observation:BACKUP:11406 at 18:56:12.241080Z. This is a complete OPEN inventory for that response, not a live resource probe or root-cause determination.
- **EXPECTED / UNVERIFIED:** Michael phone backup planned tonight September 30; Olivia/Preston October 5. Plans do not waive policy or prove recovery. Future normal recorded observations must establish recovery.
- **CHANGES:** Project documentation only. No production code, containers, incident lifecycle, credentials, tunnel configuration, or workspace permissions changed.


## USER-APPROVED ROADMAP REVISION — 2026-09-30

- **IMPLEMENTED:** Architecture roadmap updated after September 29 discussion and today's qualifications. Prior API/MCP/provenance/Investigator goals are recorded as demonstrated within their tested scope, not new public releases.
- **PRIORITIES:** Sustained reliability and evidence quality; independent reproducible experience and hands-on testers; deferred downloads/network/storage expansion; audit and policy foundations before controlled actions; additional runtimes and optional specialist agents later. Unsupported-resource/coverage honesty is an explicit acceptance goal.
- **SCHEDULED:** Automations confirmed an enabled monthly last-morning roadmap review beginning October 31, 2026, America/New_York (flexible morning window). Task: RackMarshal Roadmap Review; automation ID 6abd5ef4dde08191982ee3ff0419a2e4. Creation is verified; no future execution has yet been proven. Milestone reviews remain an active-work practice. Reviews are read-only recommendations and do not grant action authority or expand production scope.
- **BOUNDARIES:** Documentation only; no collector, incident policy, production runtime, workspace permission, or public release changed.


## COMBINED PRIVATE CLOUD PLUGIN — 2026-09-30 22:10 UTC

- **FIXED / VERIFIED:** Private archive version 0.1.1 failed with a generic import error. Added required author/interface metadata and bumped version to 0.1.2. Corrected archive imported and installed successfully as https://chatgpt.com/plugins/Plugin_a767fefb63308191bd969ec1980d47d0. Includes exactly one existing app (Connected) and one bundled Investigator skill. This supersedes the earlier combined-package-not-installed checkpoint. App binding and skill policy unchanged.
- **ACCEPTANCE:** Fresh chat https://chatgpt.com/c/6abd88ad-33d0-83ea-aefe-c36e882a9c4e returned generated_at health/status/OPEN inventory, separated ADVISORY, declined restart and manual incident mutation through Investigator, and denied airplane-engine health/root-cause coverage. Rendered answer plus visible tool trace; raw arguments/results not exported. Implicit activation and broader audience policies remain unqualified.
- **PRIVATE RECEIPT:** internal/business-combined-cloud-acceptance-20260930.json. No broader sharing, new credentials, incident mutation, or production runtime repair performed. Core public prerelease publishing remains pending.


## RC1 PUBLISHED AND DOWNLOAD-VERIFIED — 2026-09-30 UTC

- **VERIFIED:** https://github.com/RackMarshalhq/rackmarshal/releases/tag/v1.1.0-rc1 published as prerelease at public commit f4b29d4cc922531ff0068116b3624b0e548e0a99. Stable v1.0.0 remains GitHub latest; no merge or production deployment. Draft PR https://github.com/RackMarshalhq/rackmarshal/pull/8 updated with final scope through REST after gh pr edit failed on deprecated projectCards.
- **EXACT ASSETS:** Wheel, source distribution, installer bundle, local Investigator ZIP, sanitized qualification JSON and SHA256SUMS. Four package hashes match final qualification; all six downloaded assets byte-match local files. Checksums and expanded-download privacy scan PASS (414 members). Source+assets+summary+notes privacy scan PASS (601 members).
- **QUALIFICATION:** Disposable Debian 12 fresh install/reboot; stable upgrade/rollback/reupgrade; 92 wheel members byte-verified; 28 preexisting rows across 34 tables/config preserved, legitimate appended notification history retained; six HTTP checks; invalid-wheel failure retained installation/history; eleven positive MCP tools and six negative cases. CI Python 3.11/3.12/3.13 and Pages PASS. Dependency audit 29 audited/zero known vulnerabilities, local project skipped. Static analysis zero high/23 medium/82 low; medium findings contextually reviewed.
- **PRIVATE RECEIPTS:** internal/published-rc1-verification.json, internal/published-rc1-verified/, candidate-final-upgrade-rollback.log, candidate-final-mcp-proof.log. Initial dump-equality assertion was too strict for normal appended notifications; corrected checks preserve all existing rows/config and retain notification appends.
- **LIMITS:** Private combined cloud 0.1.2 separately installed/accepted; private binding and operational records excluded from release. Local ZIP desktop installation, implicit activation and broader audience controls unqualified. Disposable CT125 remains a qualification fixture, not adopted production or evidence of production recovery.


## RC1 GITHUB AND WEBSITE ANNOUNCEMENT — 2026-09-30 UTC

- **VERIFIED:** Documentation-only PR https://github.com/RackMarshalhq/rackmarshal/pull/9 squash-merged at 2db1da39ee7f657e7c7dc81b208e051bd104453f. GitHub main README announces RC1; live https://rackmarshal.com/ hero presents stable 1.0.0 and preview 1.1.0 RC1. Live install/docs pages show preview-specific commands and tagged changelog/upgrade/hosted setup links; stable installation preserved.
- **CHECKS:** Python 3.11–3.13 tests, CodeQL and Pages preview PASS before merge. Browser verified live home/install/docs; latest stable API still v1.0.0. No runtime code, private binding or operational records published. Core RC1 PR8 remains draft.
- **RECEIPT:** internal/rc1-website-publication.json.
