# PBS weekly verification evidence repair — 2026-09-30

## Recorded facts

MCP BACKUP:38 reported weekly_verification_task_not_found with null weekly status
and age. It remained OPEN before repair. Development-only inspection located the
existing root cache helper, called by proxmox-pbs-probe.service ExecStartPost and
read by the least-privileged forced-command observer.

The helper requests 100 unfiltered tasks and selects the exact verificationjob
worker homelab-backups:weekly-homelab. Read-only PBS diagnostics found no such
job within 100 tasks, but the same query at the supported maximum 1000 returns
it at positions 133 and 178. The latest exact job has status OK, starttime
1790497800 and endtime 1790498219 (2026-09-27 08:36:59 UTC). The configured job
exists with sun 04:30 schedule and ignore-verified=false. Individual snapshot
verify workers are different evidence and are not treated as weekly completion.

The installed CLI supports all/limit/output-format; typefilter is not accepted.
[Primary PBS CLI reference](https://pbs.proxmox.com/docs/proxmox-backup-manager/man1.html).

## Engineering repair and qualification

The sole runtime source change is task-list limit 100 → 1000. The existing helper
is now versioned at packaging/observers/pbs-native-verify-cache; it is a separately
promoted existing host artifact, not a new CT package module or installer action.
Exact job filtering, cache path/permissions, result selection, existing unit,
credentials and scheduling remain as before. No verification operation is run.

Five fictional fixtures execute the actual source and embedded query, covering
a result beyond the first 100 tasks, snapshot/other-job rejection, newest failure
versus older success, running job versus completed history, and host execution
error. Publication gate passes 166 test executions with zero ResourceWarnings;
target Python 3.11 passes 165/one existing staging-only Git skip.

Pinned source 5ad27c66b72bd80c9ed3187500ba00938d008876 was promoted after original
source/hash checks, a private rollback backup, timer quiescence and waiting for
in-flight work. File ownership/mode and existing timer state were preserved.
Deployment receipt/backups: /var/lib/homelab-monitor/pbs-cache-window-ie06au2w.
Normal cache refresh returned the actual job OK and age 80.169 hours. Root/cache
inspection here is engineering access; Investigator tools gain no shell access.

## Recorded recovery

Normal independent BACKUP collection and processing recorded BACKUP:38 RECOVERED
at 2026-09-30T16:47:09.364907Z (12:47 PM America/New_York), using canonical
observation:BACKUP:11333. Latest abnormal evidence remains
observation:BACKUP:11332. Recovery is observation-only; no event is invented.
Actual read-only MCP timeline/bundle verifies separate recovery evidence.

Production HTTP passes 46 checks; real MCP acceptance passes 18/18. LAN dashboard
and detail security checks pass. Status/MCP/tunnel and both relevant timers are
active. OPEN incidents now number 11: BACKUP:34, BACKUP:29, BACKUP:26 plus
PVE:36–PVE:43. Phone backups remain subject to the user's September 30/October 5
plan and unchanged seven-day policy. No baseline, incident or workspace was
manually changed.

## Advisory interpretation and limits

This was task-history truncation, not an established verification job failure.
Repair recovered visibility of a previously completed job; it did not perform a
new verification or establish present health of every backup. History remains
bounded at 1000 tasks. A future not-found result means no exact result visible
within that window, not exhaustive absence. An older successful result is not
substituted for a newer failed/running selected weekly task.

To roll back code, quiesce the existing probe timer, wait for the service to finish,
restore the backed-up original with its recorded owner/mode/hash, then restore
prior timer state. Code rollback never erases RackMarshal observation/recovery
history. Retain the deployment receipt and pbs-weekly-* metadata proofs under
evals/results. Credentials and verification job configuration need no changes.
