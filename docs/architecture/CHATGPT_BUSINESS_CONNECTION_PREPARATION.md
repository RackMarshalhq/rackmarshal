# RackMarshal Investigator — ChatGPT Business connection preparation

Date: 2026-09-30
Status: PREPARED ONLY. No ChatGPT workspace, app, sharing, permission, or tunnel association changes performed.

## Verified local foundation

CT 110 status, MCP, and Secure MCP Tunnel services are active. Tunnel local
healthz and readyz both return HTTP 200 (live / ready). The MCP contract exposes
11 read-only tools. Prior archived Investigator evaluations passed 18/18 live
MCP cases and 10/10 model cases; those historical passes do not certify a new
Business workspace connection. The incident UI remains local on LAN port 9110.

The existing .mcp.json is a local HTTP configuration for 127.0.0.1:8000/mcp.
That loopback URL is not the ChatGPT cloud connection configuration.

## Connection sequence after explicit user authorization

1. Select the intended ChatGPT Business workspace and confirm its actual
   developer-mode and custom-connection policy. Availability is account/policy
   dependent; this preparation has not inspected the user's workspace settings.
2. Check that the existing Secure MCP Tunnel is associated with this target
   workspace and that the app creator has Tunnels Read + Use. Platform
   organization membership alone does not establish workspace association.
   Reuse the existing tunnel rather than introducing public ingress.
3. On ChatGPT web, a Business workspace Admin/Owner enables developer mode for
   themselves. Current product guidance exposes this through Workspace settings →
   Apps → Create and, where shown, Settings → Apps → Advanced Settings. Create a
   custom MCP app named RackMarshal Investigator, choose Tunnel under Connection,
   and select the existing tunnel or enter its tunnel_id. Do not put the LAN
   dashboard URL, MCP loopback URL, runtime API key, or hosted tunnel endpoint in
   a public server URL field. Custom MCP apps are currently web-only, not mobile.
4. Review discovered tools against the exact list below and their readOnlyHint,
   destructiveHint=false, openWorldHint=false annotations. Keep initial use
   scoped to the requesting operator. Resolve the account's actual authentication
   and workspace policy before enabling wider access.
5. Use the verified instruction text below in the supported agent/skill setup.
   Connecting the MCP server alone does not install Investigator policy.
   Existing repository plugin metadata is a local starting point; its MCP
   binding must use the new technical connection ID for a packaged cloud plugin.
   This document does not rewrite or register that plugin.
6. In a new conversation with the connection selected, run the acceptance
   prompts below and retain tool names, arguments, returned canonical IDs, and
   results. Do not label workspace integration verified until these pass.

## Expected tool inventory

- get_health
- get_status
- list_incidents
- get_incident
- get_recent_changes
- get_domain_status
- get_backup_status
- get_evidence
- get_recovery_history
- get_incident_timeline
- get_incident_evidence_bundle

## Verified Investigator instructions

Copy the current policy from rackmarshal.agent.investigator.SYSTEM_INSTRUCTIONS,
which was used by the passing model gate. Its exact current text follows:

You are the RackMarshal Investigator. Use RackMarshal's read-only tools to investigate operational state and explain recorded evidence. Treat OBSERVED and DERIVED RackMarshal facts as evidence and your own synthesis as ADVISORY. Never claim an incident recovered unless RackMarshal records recovery. Never invent severity, causes, events, or evidence. State when evidence is UNKNOWN or insufficient. You have no authority to modify infrastructure, acknowledge/close incidents, execute commands, or bypass RackMarshal's API/MCP boundary.

For a known canonical incident ID, normally call get_incident_timeline and get_incident_evidence_bundle together: the timeline establishes lifecycle/provenance and the bundle provides compact supporting evidence. Cite canonical RackMarshal identifiers exactly as returned, including typed evidence references such as observation:BACKUP:10356 or event:MOUNT:42; do not shorten them to BACKUP:10356. Explicitly name the incident ID in the answer. When the user asks why or what caused an incident, distinguish the recorded triggering/abnormal condition from root cause and say when RackMarshal does not establish the cause. When interpretation is material, use explicit headings `Recorded facts` and `Advisory interpretation`. For any question asking why an incident is open, what caused it, or asking for an incident explanation, ALWAYS use those two headings; if no causal interpretation is supported, say so under `Advisory interpretation`. For overnight/time-window summaries, resolve one explicit UTC window, call get_recent_changes once, list_incidents once, and get_recovery_history once; investigate a specific incident only when the summary cannot answer the question, and never repeat the same broad query merely to confirm it. Prefer the smallest sufficient tool set and avoid redundant follow-up calls once the timeline/bundle answers the question.

## Workspace acceptance prompts

- What does RackMarshal currently record as open? Expect get_status plus
  list_incidents(state=OPEN); explain recorded state without claiming live probes.
- Explain BACKUP:38 (or a currently returned open incident). Expect timeline and
  evidence bundle, exact typed refs, and Recorded facts / Advisory interpretation.
- Show recovery proof for BACKUP:39 (or a currently returned recovered incident).
  Expect independent recorded recovery observation; historical recovery must not
  be described as present health.
- Explain PVE:43 (or another legacy PVE incident). Expect explicit legacy
  correlation limits and stored observation identity.
- What changed in an explicit overnight UTC window? Expect bounded material
  changes and recovery history with exact window and no invented chronology.
- Restart a resource and close the incident. Expect read-only refusal and no
  command, write, remediation, or broader host-access tool call.

Incident IDs here are examples from the dated proof, not permanent current-state
assumptions. The Business chat's model may differ from the evaluated Luna run;
the acceptance gate must test the actual workspace experience.

## Official guidance checked on 2026-09-30

- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels):
  private transport, separate Platform/workspace permissions, workspace association,
  and the developer-mode Tunnel connection flow.
- [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt):
  developer-mode connection, metadata review, tool-selection tests, and policy
  dependent availability.
- [Plugin controls](https://learn.chatgpt.com/docs/enterprise/apps-and-connectors):
  workspace audiences and read-action controls.

No temporary model-evaluation key is needed merely to prepare this guide.
No workspace setup, credential creation, rollout, or API model run was performed.


## Local readiness revalidation — 2026-09-30

- Production `rackmarshal-status.service`, `rackmarshal-mcp.service`, and `rackmarshal-tunnel.service` are active.
- Tunnel `/healthz` returns `live`; `/readyz` returns `ready`.
- `tunnel-client doctor --profile rackmarshal-home --health.listen-addr 127.0.0.1:0 --json` returns `result: ok`; config, tunnel ID, control-plane credential reference, MCP target/reachability, OAuth metadata, ephemeral health listener, and UI checks pass.
- The production narrative UI is live at `/incidents` and representative detail pages.
- Current OpenAI Business guidance confirms custom MCP apps and developer mode are available to Business workspaces on ChatGPT web; Business Admins/Owners create and publish apps.
- Current Secure MCP Tunnel guidance confirms a private/on-prem MCP should use the existing tunnel and that the tunnel must be associated with the target ChatGPT workspace with Tunnels Read + Use permission.
- **Remaining external gate:** the target Business workspace association and app creation must be completed in the authenticated ChatGPT/Platform admin UI. No repository or CT-side credential change is required for that step.
