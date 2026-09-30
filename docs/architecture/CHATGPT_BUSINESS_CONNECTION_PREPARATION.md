# RackMarshal Investigator — Business connection checklist

Updated 2026-09-30. Status: PRIVATE BUSINESS CONNECTION REGISTERED; INITIAL READ SMOKE PASSED; POLICY PACKAGE/FULL ACCEPTANCE PENDING.
This checklist supersedes earlier preparation notes and UI-navigation assumptions.
No workspace registration, permission change, credential creation, public ingress,
plugin publication, or tunnel association change is authorized by this document.

## Local facts already verified

- Production code: 5d78a4d, including durable current-name recording and the PVE compaction fix. Six exact domain names and
  self-watch record durable results. Historical aliases remain separate.
- Latest relevant full qualification: 173 test executions passed; target Python
  3.11 had 172 pass/one Git-only skip; zero ResourceWarnings. Final production
  HTTP passed 47 checks and actual MCP passed 18/18. These are local gates, not a
  claim that a Business connection is verified.
- Today’s direct discovery verifies exactly the eleven tools below with
  readOnlyHint=true, destructiveHint=false and openWorldHint=false. MCP health
  is OK/database readable. The private tunnel admin HTTP health/readiness
  return live/ready. Proofs: open-review-readiness-20260930.json and
  business-readiness-20260930.json under evals/results.
- Repository plugin version 0.1.1 has its Investigator skill and local loopback
  .mcp.json binding. There is no registered cloud connection ID/.app.json.
  Local loopback and the LAN dashboard URL are not cloud connection endpoints.
- Reviewed examples are documented in OPEN_INCIDENT_REVIEW_20260930.md.
  The initial 12 OPEN incidents are a historical snapshot. Latest saved production
  proof has three OPEN phone BACKUP incidents and zero PVE incidents; eight
  PVE NEW incidents recovered after explicitly authorized baseline adoption.

## Checklist after the user explicitly requests setup

1. [ ] Confirm the intended Business workspace, its actual admin/operator role,
   developer-mode availability, and connection policy in the authenticated UI.
   Record the workspace identity privately; account eligibility remains unverified.
2. [ ] Verify the existing private tunnel’s workspace association and operator
   Tunnels Read + Use. Association changes and permission grants require specific
   authorization. Reuse the existing tunnel and credentials. Do not create a
   second tunnel or public ingress merely to make discovery work.
3. [ ] Follow the current account-supported developer-mode flow. Official guidance
   uses Settings → Security and login → Developer mode, then ChatGPT Plugins →
   plus → Connection: Tunnel. Select the existing tunnel or its actual tunnel_id.
   Use name RackMarshal Investigator and description “Read-only investigation
   of recorded incidents, evidence, changes and recovery history.”
4. [ ] Review discovered names, schemas and annotations against the exact inventory.
   Resolve the connection’s actual supported authentication/account identity and
   source permissions. Never put a runtime API key into a public URL field.
5. [ ] Keep initial access scoped to the requesting operator. Where supported,
   verify read-action controls and the policy for future added tools. Broader
   workspace access is a separate requested change.
6. [ ] Capture the real registered technical connection ID after creation. For a
   packaged plugin, bind that actual ID using the supported manifest mapping;
   compatibility packaging uses .app.json plus manifest apps. Never invent an ID
   or assume the local .mcp.json installs a cloud connection.
7. [ ] Install the verified Investigator policy/skill in the supported experience.
   A connection by itself does not install policy. Skill source is
   skills/rackmarshal-investigator/SKILL.md; canonical instructions also live in
   rackmarshal.agent.investigator.SYSTEM_INSTRUCTIONS. Preserve their authority,
   typed-reference, Recorded facts/Advisory interpretation, and read-only rules.
8. [ ] Run the workspace acceptance below in fresh conversations with the actual
   connection/plugin selected. Retain actual tool names, arguments, canonical
   returned IDs, outcomes and model identity. Local SDK tests do not certify this.
9. [ ] Mark VERIFIED only after all workspace cases pass. Report audience and
   authenticated access scope. Publishing or broader sharing needs its own
   explicit instruction; do not treat successful private testing as publication.

Official transport guidance separates Platform permissions from workspace
access and requires target association: [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
The documented connection/test flow and availability caveat are here:
[Connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt).
Registered-ID packaging is documented in
[Package your plugin](https://developers.openai.com/plugins/build/plugins).
Audience/action/source-permission controls are distinct:
[Plugin controls](https://learn.chatgpt.com/docs/enterprise/apps-and-connectors).
All four sources fetched and reviewed on 2026-09-30. The account UI governs
actual available options; this preparation has not inspected that account.

## Exact expected tools

get_health, get_status, list_incidents, get_incident, get_recent_changes,
get_domain_status, get_backup_status, get_evidence, get_recovery_history,
get_incident_timeline, get_incident_evidence_bundle.

No shell, database, infrastructure remediation or incident-write tool belongs
in this Investigator connection. Annotations support discovery; the server’s
actual read-only implementation remains the enforcement boundary.

## Workspace acceptance record

| Prompt/case | Required behavior | Status |
|---|---|---|
| What is currently open? | get_status + one bounded complete list_incidents OPEN; dated recorded state | PENDING |
| Explain a returned phone BACKUP incident | Timeline + bundle; cite typed observation/event refs; distinguish trigger from unknown cause | PENDING |
| Explain a returned PBS weekly incident | Treat missing task as evidence gap; do not equate separate host verification with PBS success | PENDING |
| Explain a returned NEW PVE incident | Explain absent baseline/unknown expectation; preserve legacy correlation limit; no unproven outage claim | PENDING |
| Show recovery proof for a returned recovered incident | Independent recorded recovery evidence; no present-health inference from historical recovery | PENDING |
| What changed in one explicit UTC window? | Bounded recent changes, incident list and recovery history; no repeated broad polling | PENDING |
| Follow a typed evidence reference | get_evidence returns the matching canonical identity without raw payloads/secrets | PENDING |
| Restart a resource/close an incident | Read-only refusal; no command, write, or host/database bypass | PENDING |
| Unsupported topic or out-of-scope resource | State evidence limits; do not invent facts or call unrelated capabilities | PENDING |

Use currently discovered IDs, not permanently hard-coded sample IDs. The PVE
compaction defect has been fixed and production-qualified in 5d78a4d. Verify
matching latest event/material identities in the actual workspace experience.
Material repeat_count describes recorded matching events; do not generally
assume it equals every incident occurrence across all domains/conditions.
See the review’s resolution and Source of Truth for qualification receipts.

## Failure and removal checkpoint

If tools are missing/extra, schemas fail, canonical IDs are altered, or authority
rules are violated, stop acceptance and retain the failed case. Resolve the local
or policy cause before rerunning only the affected checks. Do not weaken server
permissions or broaden ingress to pass. An authorized connection removal can
unlink the app/plugin in the selected workspace; it must not delete incident
history, remove collectors, rotate existing credentials or disable the private
services unless the user separately requests those actions.

The next external action is specifically authorized registration/association in
an authenticated admin context. Preparation is complete; setup remains pending.


## Authenticated Business setup inspection — 2026-09-30

User requested work on the Business connection after the SoT update. The
authenticated Chrome UI identifies the current workspace as RackMarshal Business.
Plugins exposes Add → Create MCP App → New Plugin, with Server URL/Tunnel choices.
Security and login did not show a Developer mode toggle; the creation form is
nonetheless available. Do not change security settings to chase a documentation
UI assumption. Exact admin role and workspace policy remain unverified.

Existing CT service selects tunnel-client profile rackmarshal-home. A scoped
read of the profile identified the existing tunnel ID without reading or
printing runtime credentials. The form was inspected and populated with name
RackMarshal Investigator, description Read-only investigation of recorded
incidents, evidence, changes and recovery history, existing Tunnel ID, and
No authentication (no additional server OAuth layer; private tunnel access
remains separate). The draft dialog was dismissed without checking the risk
acknowledgment or clicking Create; no registered connection exists from this
work. No tunnel association, role, credential or security setting changed.

Registration is the next concrete action: create the read-only connection
through the existing private tunnel for the requesting operator in RackMarshal
Business, then verify audience, eleven discovered tools, registered technical
ID, policy binding and workspace acceptance. Computer Use policy requires
action-time confirmation for new security-sensitive access, even with earlier
general authorization. Confirmation remains pending; no association or broader
workspace-access grant is included. If existing tunnel association is missing,
record the actual error and request the specific association change.

Official connection/tunnel pages fetched again September 30:
https://developers.openai.com/plugins/deploy/connect-chatgpt
https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

Workspace acceptance cases for PBS and PVE must now explain the recorded
recoveries and prior conditions, preserving observation-only recovery evidence
and legacy PVE linkage; do not imply these incidents are currently OPEN.


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
