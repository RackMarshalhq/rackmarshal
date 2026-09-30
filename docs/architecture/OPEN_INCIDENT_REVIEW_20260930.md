# Open incident evidence review — 2026-09-30

Read-only MCP snapshot: 16:11:40 UTC / 12:11 PM America/New_York.
Authority: RackMarshal observations are OBSERVED; events/incidents are DERIVED.
Interpretation and suggested next steps below are ADVISORY. This is a dated
snapshot, not a live resource probe.

## Recorded facts

All 12 returned incidents are OPEN: four BACKUP, eight PVE. Pagination is complete
(next_cursor null). Every incident was reviewed using its timeline and evidence
bundle. None contains recovery evidence or an INCIDENT_RECOVERED item.

BACKUP evidence observation:BACKUP:11314 was observed at
2026-09-30T16:10:12.448475Z. PVE evidence observation:PVE:11313 was observed at
2026-09-30T16:10:12.423813Z. PVE freshness was OK (88 seconds versus a 900-second
policy); a later targeted BACKUP read confirms freshness OK (45 seconds versus
900) at observation:BACKUP:11317, 16:15:32.983651Z. The later read is a separate
readiness check, not a replacement for the incident cohort snapshot.

| Incident | Resource | Latest recorded condition | Recorded occurrences | Latest event evidence |
|---|---|---|---:|---|
| [BACKUP:38](http://192.168.50.110:9110/incidents/BACKUP:38) | PBS native weekly verification | weekly_verification_task_not_found; status/age unknown | 112 | `event:BACKUP:1598` |
| [PVE:43](http://192.168.50.110:9110/incidents/PVE:43) | rackmarshal-reconcile-accept | NEW; expected status unknown; observed running | 143 | `event:PVE:1593` |
| [PVE:42](http://192.168.50.110:9110/incidents/PVE:42) | rackmarshal-reconcile-final | NEW; expected status unknown; observed stopped | 143 | `event:PVE:1592` |
| [PVE:41](http://192.168.50.110:9110/incidents/PVE:41) | rackmarshal-reconcile-qual | NEW; expected status unknown; observed stopped | 143 | `event:PVE:1591` |
| [PVE:40](http://192.168.50.110:9110/incidents/PVE:40) | rackmarshal-fullcycle-qual | NEW; expected status unknown; observed stopped | 143 | `event:PVE:1590` |
| [PVE:39](http://192.168.50.110:9110/incidents/PVE:39) | rackmarshal-delivery-final | NEW; expected status unknown; observed stopped | 143 | `event:PVE:1589` |
| [PVE:38](http://192.168.50.110:9110/incidents/PVE:38) | rackmarshal-delivery-qual2 | NEW; expected status unknown; observed stopped | 143 | `event:PVE:1588` |
| [PVE:37](http://192.168.50.110:9110/incidents/PVE:37) | rackmarshal-delivery-qual | NEW; expected status unknown; observed stopped | 143 | `event:PVE:1587` |
| [PVE:36](http://192.168.50.110:9110/incidents/PVE:36) | rackmarshal-migration-drill | NEW; expected status unknown; observed stopped | 143 | `event:PVE:1586` |
| [BACKUP:34](http://192.168.50.110:9110/incidents/BACKUP:34) | Phone backup (michael) | 181.466 h > 168 h policy (7.56 days) | 148 | `event:BACKUP:1595` |
| [BACKUP:29](http://192.168.50.110:9110/incidents/BACKUP:29) | Phone backup (preston) | 241.87 h > 168 h policy (10.08 days) | 538 | `event:BACKUP:1597` |
| [BACKUP:26](http://192.168.50.110:9110/incidents/BACKUP:26) | Phone backup (olivia) | 275.541 h > 168 h policy (11.48 days) | 569 | `event:BACKUP:1596` |

The BACKUP rows use direct event IDs with opening/latest observations. Phone
backup directories exist according to get_backup_status; existence does not
establish that a recent backup completed. Their age exceeds policy. The weekly
PBS condition has unknown status/age and the recorded probe error above.
The separately named host-backup verification reports success; that is a
different verification process and does not establish PBS weekly success.

All PVE incidents concern LXC IDs 117–124 and have no baseline/expected status.
Seven are observed stopped; ID 124 is observed running. All opened at
2026-09-30T03:27:40.190862Z, using observation:PVE:10996. Their event linkage is
explicitly LEGACY_RESOURCE_TIME_CORRELATION; no stored direct opening/latest
event foreign key is invented. Null opening_changes/latest_changes in the
incident list are not missing observations: the correlated event evidence
contains the reported status. The resource names suggest qualification/drill
containers, but names alone do not establish disposal authorization.

## Advisory interpretation

1. **Actionable phone backup staleness:** BACKUP:34 (Michael), BACKUP:29 (Preston),
   and BACKUP:26 (Olivia) have recent observations of old backup data. Review each
   phone's normal backup availability and schedule. The recorded trigger is age,
   not an established device, network, credential, or scheduling root cause.
   Restore normal backup generation; let independent subsequent observations
   and the normal comparator/processor establish recovery.
2. **Incomplete weekly verification evidence:** BACKUP:38 establishes inability
   to find the expected weekly task, not a proven failed verification job.
   Next engineering investigation should distinguish a genuinely absent run
   from task-history window, naming/filter, retention or permission limitations
   in the forced-command observer. Its returned task history and selection
   criteria are not exposed by current Investigator tools. No collector defect
   or successful weekly verification is established by the available evidence.
3. **PVE inventory-policy review:** PVE:36–PVE:43 are NEW inventory incidents.
   Source review of compare() confirms NEW means present in observation and
   absent from baseline; it does not mean stopped against an expected-running
   baseline. Decide whether these resources are intended inventory or disposable
   qualification infrastructure. Do not suppress the detector or edit incidents
   to clear the count. Any authorized baseline change/cleanup must be followed
   by normal independent collection and processing; resource removal is not
   performed by this review.
4. **Confirmed bounded evidence-compaction bug:** All eight PVE bundles report
   143 incident occurrences but material compaction ends at the prior event
   (142 repeats), while latest_abnormal_evidence correctly contains the newest
   event. Event detection time (e.g. PVE:1593 at 16:10:12.685Z) exceeds incident
   last_abnormal_at (observation time 16:10:12.423813Z). Source inspection locates
   _incident_events()'s event-time upper cutoff. An isolated fixture reproduces
   count 2/latest event 8 versus compacted count 1/latest event 7. This is a
   presentation-selection defect, not evidence that the incident recovered or
   that current processing is stuck. A bounded fix should select lifecycle
   evidence using authoritative observation boundaries/resource identity,
   preserve legacy-correlation limits, and exclude later incident cycles. Test
   detection lag, OPEN/recovered cases, event type/resource collisions, and
   re-opened lifecycles before code promotion. No fix is deployed by this review.

No current lifecycle closure defect is established. Fresh observation IDs and
new latest events show the reviewed conditions continue to be processed.
Occurrence counts are recorded detections across polls, not 143 separate
resource failures. Causal evidence remains limited to the returned conditions.

## Verification and retained evidence

The review made 28 read-only MCP calls: status, complete open list, BACKUP status,
PVE domain status, and timeline/bundle for every incident. Targeted readiness
adds health and BACKUP domain freshness; server discovery verifies the exact
11-tool inventory and readOnlyHint=true/destructiveHint=false/openWorldHint=false.
Health returns OK/database readable. No raw payload_json or cached AI narrative
is retrieved. Engineering reproduction uses an in-memory fictional fixture,
with ResourceWarnings treated as errors; no production ledger is opened by
shell or SQLite. No infrastructure, baseline, incident, credential or workspace
mutation occurred. No production redeployment or redundant full-suite run was
needed for this read-only review and documentation update.

Receipts: evals/results/open-incidents-review-20260930.json,
open-review-readiness-20260930.json, and
open-review-pve-timestamp-fixture-20260930.json.
