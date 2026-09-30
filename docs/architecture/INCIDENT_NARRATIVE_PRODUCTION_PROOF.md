# Deterministic incident narrative production gate


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

Rollback: restore the backed-up api/v1.py, ui/dashboard.py, and ui/incidents.py to the installed package, then restart rackmarshal-status. The additive ui/narrative.py can remain unused. No database or configuration migration occurred.
