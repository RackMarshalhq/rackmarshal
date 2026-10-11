# Static review: remaining diagnostic and execution boundaries

This follow-up builds on local commit `95a3bc8`, separately from frozen RC5
`f9ccecb`. It does not alter the frozen release artifacts or their receipts.
Bandit findings remain visible; reviewed assumptions are not suppressed.

## Administrator-controlled commands and configuration

The original eleven B607 matches comprise three runtime uses, five operator
script uses and three test uses:

| Paths | Boundary and disposition |
| --- | --- |
| `api/status.py:unit_active_state` | Invokes `systemctl show` with separate arguments and a five-second timeout. An attacker needs control of the launch PATH/executable to substitute code. Keep a trusted service environment; no remotely supplied shell expression was found. |
| `domains/ha/collector.py:load_credentials`, `notifications/delivery.py:load_ha_credentials` | Resolve Bash via PATH and source an administrator-selected credential file. This file is executable shell configuration. Its contents must be trusted and protected from less-trusted writers. Positional path arguments avoid path interpolation into the constant shell program; they do not sanitize the sourced program. |
| `scripts/promote-package-files.py`, `scripts/release-candidate-gate.py`, `scripts/release-privacy-gate.py` | Resolve Git or systemctl in an explicitly invoked operator environment. Repository and executable selection are administrator authority. Running these as root with an attacker-writable PATH could execute attacker code as root; no remote input-to-PATH route was established. |
| `tests/test_package_promotion.py`, `tests/test_release_candidate_gate.py` | Git calls in synthetic repositories under the developer's test environment. No product runtime command-execution boundary is crossed. |

Additional B603 findings use argument lists, package module commands or explicit
operator-selected Python/comparator/explainer programs. Executable selection is
an intentional configuration capability, not a promise to safely run untrusted
programs. The Home Assistant shell loader differs from generic key-value config
and PVE/PBS credential readers; the latter do not evaluate shell code.

The installer creates new configuration root-owned (0640, service-readable),
creates the non-login RackMarshal service account, and preserves existing
configuration. Packaged units use that account, absolute Python entrypoints,
NoNewPrivileges and filesystem protections. Existing configuration permissions,
service overrides and administrator PATH remain outside that guarantee.

Disposition: document these legitimate trust assumptions in CONFIGURATION.md.
Do not silently replace shell configuration with a different parser, reject
legitimate operator executables, or claim a broad privilege boundary from
argument-list usage. Such compatibility changes would need a separate design
decision. No demonstrated remote command-injection defect remains in this
reviewed category.

## Timeouts and diagnostics

The [diagnostic review](STATUS_DIAGNOSTICS_FOLLOWUP.md) records fixed paths:
`attach_backup_summary` now exposes summary derivation failure as explicit
UNKNOWN evidence; `load_stale_after_seconds`/`build_freshness` report invalid
identified policy as MISSING with a policy-gap reason. Timestamp facts remain,
self-watch cannot infer recovery from the gap, and dashboard wording identifies
the actual missing policy. Entirely absent optional metadata retains the
existing documented 900-second default; this is intentional compatibility,
not a claim that all missing configuration is rejected.

The [subprocess review](SUBPROCESS_TIMEOUT_REVIEW.md) records every affected
runtime category, limits and standalone script disposition. New bounded
credential, comparator, packet and cycle calls reject incomplete results.
The existing finite MOUNT stage durations now use managed local cleanup.
Existing SSH and optional-explainer leaf calls retain their durations and
soft-error/fallback contracts. They inherit an enclosing managed stage group
when present, but their own leaf timeout only guarantees direct-child handling;
local descendants and remote jobs are not universally canceled. A configurable cycle-stage limit permits larger inventories;
no universal total-cycle SLA is claimed. Standalone Git reads have 30-second
limits. The complete release privacy scan remains wall-time uncapped but
subject to its existing archive/size budgets; its result is mandatory before
a gate can succeed. Operator-controlled builds, migrations and long
qualification windows are not assigned arbitrary short deadlines.

No further material design decision is required to retain these isolated
fixes. Before publishing a new candidate, workload-specific timeout sizing,
POSIX/Linux installation behavior and exact-artifact qualification must be
reviewed. Replacing shell credential configuration, forbidding operator
executables, changing optional-metadata defaults or guaranteeing cancellation
of remote/detached jobs would be separate compatibility/architecture decisions.
Final validation is retained with the development receipt. `Type=oneshot` alone does not supply a finite
startup timeout: systemd disables its default startup timeout for that type.
The existing packaged domain/notify units have no explicit TimeoutStartSec.
See the [systemd service reference](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#TimeoutStartSec=).

Timeout failure is not proof that a child made no changes. Previously committed
observations/history must remain retained, and a timed-out processing stage
must not be converted into empty healthy evidence or a success receipt.
No local timeout can prove cancellation of an already dispatched remote action,
or guarantee prompt completion of uninterruptible kernel I/O. This development
work does not kill or change any existing deployed process.

## Final validation for the residual follow-up

The aggregate publication gate (validation only, no publication) passed 317
unit/integration tests, staging smoke, compilation and source privacy checks on
macOS arm64/Python 3.14.7. ResourceWarning was treated as an error; final logs
contain no ResourceWarnings or ignored resource-finalizer exceptions.
Independent review passed the final 13 process tests and separately seven
diagnostic, six hardware-result and three existing cycle tests, with no
remaining blocker in the inspected changes. Actual synthetic child processes
verify both nested timeout directions and preserved BACKUP soft-error and
optional-explainer fallback behavior. No remote production calls were made.

The final same-scope Bandit 1.9.4 scan covers 19,908 lines, has no analysis errors,
and reports **0 high, 24 medium, 166 low**, exit 1. Static analysis is not clean.
No findings were suppressed. Medium dispositions: the original sixteen SQL
patterns plus two SQL-looking strings in synthetic timeout fixture code, three
trusted test exec sites, one trusted test eval site, and two loopback HTTP test
calls. Low dispositions remain assertion guards/diagnostic assertions,
subprocess construction and trusted PATH, deliberate cleanup exception handlers
and four false-positive/synthetic password strings. The prior silent
except/continue policy fallback no longer hides identified invalid metadata.

Absence of a direct subprocess scanner match after routing through a helper is
not a safety result; reviewed behavior and regression tests support the change.
No dependency audit, real TLS handshake, Debian deployment, production load,
hosted-client acceptance or new sustained qualification is claimed. Frozen RC5
artifacts and its historical receipts remain separate and unchanged.
