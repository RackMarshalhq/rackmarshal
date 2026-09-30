# Durable current-unit cycle results

Domain template and existing optional self-watch units attach the same packaged
20-cycle-health.conf drop-in. ExecStopPost calls the existing recorder with %n,
so the durable key is the actual service instance, never an old alias.

--from-systemd consumes SERVICE_RESULT, EXIT_CODE, EXIT_STATUS and optional
INVOCATION_ID supplied to the final hook. SUCCESS requires success/exited/0;
other supplied outcomes record FAILED. Missing SERVICE_RESULT rejects the write.
Numeric CLD exit codes are 1 exited, 2 killed, 3 dumped; nonnumeric signal names
remain in detail_json. Existing explicit --state callers remain compatible.

The recorder updates only cycle_health. It preserves prior success/failure times
and cumulative recorded failure_count. It does not create incidents or change
observations, notifications, or infrastructure. A successful cycle is execution
evidence and does not establish recovery of an incident. Historical unit rows
remain separate and are never rewritten or renamed.

The hook's leading dash logs recorder failure without replacing the main result.
If a write fails, the ledger remains at its last recorded result; operators must
use timestamps and the journal rather than infer a new successful recording.
The recorder inherits the service user and filesystem sandbox, with no extra
writable paths. No credentials or dependencies are added.

Installer bundles include drop-in directories recursively. Installation attaches
the domain hook and attaches self-watch only when that unit already exists; it
does not create or enable self-watch. Uninstall removes only our named drop-ins.

For existing installations, first qualify and promote the recorder Python file
through REPRODUCIBLE_CODE_PROMOTION.md. Unit drop-ins are a separate, explicitly
backed-up deployment: snapshot timer states and base-unit hashes, stop relevant
timers and wait for in-flight cycles, copy/hash the two pinned drop-ins, verify
units and daemon-reload, then restore prior active timers. Preserve base units.
Keep source and unit receipts separately. On failure restore original drop-ins,
reload and restore prior runtime before considering code rollback. Rollback
never deletes recorded cycle results. Do not redeploy unchanged base units.

Qualification includes isolated ledger regression tests and disposable systemd
failure, recovery, and recorder-error cases under the cycle security directives.
Real acceptance runs normal cycles and reads their recorded results via /status;
fixture results must never be written to the production ledger.
