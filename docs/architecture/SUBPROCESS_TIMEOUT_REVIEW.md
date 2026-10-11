# Local subprocess timeout follow-up

This development change follows frozen RC5. It does not modify or inherit the
acceptance of the frozen candidate, its artifacts, or its qualification evidence.

## Runtime inventory and limits

| Call sites | Limit in seconds | Result on timeout |
| --- | --- | --- |
| HA collector and notification delivery credential shell | 30 | Typed collection/delivery failure; no credentials returned |
| HA/PVE event and incident comparator children | 120 | Failed processing; no empty comparison substituted |
| Notification queue packet builder | 120 per packet | Enqueue failure; no successful packet substituted |
| PVE, HA, BACKUP, ZFS cycle child stages; HARDWARE collector, ledger processor and queue/delivery stages; self-watch queue/delivery stages | 300 per child by default | Failed/incomplete stage, never successful partial JSON |
| MOUNT cycle | Existing collector 180, processor/enqueue 60, delivery default 45 | Existing timeout/failure result; durations retained |
| BACKUP SSH probe | Existing 30 | Existing soft probe error preserved; no positive recovery evidence |
| HARDWARE/ZFS and MOUNT SSH probes | Existing 20 | Existing collector error/unknown behavior preserved |
| Notification explainer | Existing argument, default 20 | Existing catchable explanation timeout; deterministic fallback remains available |
| API status systemctl query | Existing 5 | Existing diagnostic failure contract; separate diagnostic implementation |

`RACKMARSHAL_STAGE_TIMEOUT_SECONDS` overrides the new 300-second per-child cycle
limit. It must be finite and positive. Large inventories and notification
backlogs may legitimately require more time. The setting is an environment
variable for the cycle process, not a newly parsed configuration-file key. It
does not change the fixed credential/comparator/packet limits, the MOUNT limits,
or existing network/SSH timeouts. No systemd unit is changed by this follow-up.

The packaged domain and notification services are `Type=oneshot` and have no
explicit `TimeoutStartSec`. Thus their files do not establish a finite overall
cycle bound. Per-child limits do not imply an overall cycle deadline: for
example, HA may process a backlog one bounded processor call at a time, and a
queue pass can build multiple individually bounded packets.

## Cleanup and retained state

Newly bounded runtime children and the existing hard-failure MOUNT stage wrapper
use `rackmarshal.process.run`. Existing finite SSH leaf probes and the optional
explainer retain `subprocess.run` to preserve their soft-error/fallback contracts.
A top-level managed call starts a
new POSIX session/group. Nested managed calls share that group after checking
the inherited owner PID/session against the live process and ensuring the
supervisor's session is different. Stale, malformed and same-session markers
cannot select the caller's group. The internal `_RACKMARSHAL_PROCESS_OWNER_*`
variables are execution bookkeeping, not operator configuration or an isolation
boundary against malicious code. They must not be set by users or credential
scripts.

An outer timeout kills its managed process group. A nested timeout kills that
same group, including the nested supervisor; the outer caller receives a
nonzero exit and reports failure. The existing finite SSH/explainer leaf calls
are deliberately different: they inherit the enclosing managed group, so an
outer stage timeout can clean up ordinary local descendants, but their own
`subprocess.run` timeout kills only the direct child. Its descendants may retain
pipes or continue until the enclosing stage deadline. Standalone leaf calls have
no such outer bound; remote SSH job cancellation is not established. Keeping
these calls preserves BACKUP's soft `_error` result and the optional explainer's
catchable timeout without terminating their parent on the shorter leaf deadline.
The current delivery path uses cached explanation state and deterministic facts;
it does not invoke the legacy explainer helper synchronously.
Explicit child environments retain this
bookkeeping. Cleanup waits at most five additional seconds. Managed-runner timeout exceptions
omit command arguments and captured stdout/stderr; its adapters emit fixed failure
messages. Partial success-looking output is never accepted after timeout.

This cannot guarantee cancellation of a remote SSH observer, intentionally
session-detached processes, or kernel-uninterruptible I/O. The diagnostic
systemctl call and standalone publication tools are not claimed to provide the
same descendant-group cleanup. This is not a hostile-process sandbox.

Timeout is not a transaction rollback. Previously committed observations,
events, notifications or incident updates remain retained; an already delivered
notification may have reached its recipient before a process was interrupted.
Normal reconciliation/retry must inspect retained state. No timeout itself
creates a positive observation, closes an incident, or establishes current
resource health.

## Standalone script inventory

- `promote-package-files.py`: Git reads now have 30-second limits. Existing
  systemctl 30-second, isolated Python path query 15-second and HTTP/MCP
  acceptance subprocess 180-second limits are unchanged. Readiness uses its
  existing monotonic deadline. These commands remain operator-invoked.
- `release-candidate-gate.py`: Git identity/status reads now have 30-second
  limits; timeout fails the gate. Its complete privacy-scan child remains
  uncapped by wall time: archive/member/expanded-byte budgets bound scan work,
  but slow filesystem I/O is not given an arbitrary publication deadline.
  A completed privacy result is still mandatory before success/checksums.
- `release-privacy-gate.py`: source Git enumeration now has a 30-second limit;
  failure cannot produce PASS.
- Other Python scripts have no subprocess calls. Shell installer, uninstaller,
  builder and publication commands retain their existing operator-controlled
  execution. Installation/migration/package building and long qualification
  windows are not assigned short blanket time limits.

## Regression evidence

Synthetic tests exercise byte/text stdin and results; nonzero exit handling;
an actual shell and grandchild retaining output pipes; nested outer-first and
inner-first timeouts; explicit environment propagation; stale/same-session
marker rejection; BACKUP soft timeout and catchable optional-explainer timeout
with deterministic cached fallback inside managed parents; timeout redaction; legitimate stage override validation;
all newly bounded cycle wrappers rejecting partial JSON; credential and packet
builder typed failures; comparator timeout retaining an OPEN incident; and
preservation/integrity of already committed SQLite evidence after interruption.
No fixture calls production, a remote observer, or an external endpoint.
