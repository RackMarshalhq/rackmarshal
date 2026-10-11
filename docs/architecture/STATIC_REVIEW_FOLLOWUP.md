# RC5 static-analysis follow-up

This is a source review of frozen RC5 `f9ccecbcbded212610bf4cf9add412ddd958894f`, with changes prepared separately. It does not alter the frozen candidate, its artifacts or qualification evidence. Findings are classified by reviewed dataflow, not suppressed to obtain a clean scanner result.

## Scope and limits

Original scan: Bandit 1.9.4, Python 3.13.5, recursive Python analysis of `rackmarshal`, `scripts`, `tests`, `build_support`; 18,849 lines; zero analysis errors; **0 high, 34 medium, 173 low**; exit 1. Shell/YAML, dependencies, running infrastructure, authenticated hosted clients and exploitation were outside this scan. Static review is not a security certification. Counts below refer to the frozen report; lines may move in this follow-up.

All 173 low findings and 20 non-URL medium findings were grouped and inspected at their call sites, with relevant command construction/schema/exception handling read. “Reviewed” does not mean every adjacent code path was exhaustively audited or dynamically tested.

## URL handling

Fourteen original B310 findings were reviewed: eight runtime clients, four standalone proof/readiness script sites and two local HTTP fixture calls. A two-server synthetic control confirmed that stock urllib forwards an Authorization header on a cross-port 302 redirect returned by the configured endpoint. This proves credential forwarding under that prerequisite, not attacker control of a deployed endpoint or an actual disclosure. The POST body was dropped by urllib's normal 302 behavior in that control.

All eight runtime sites now use a shared validated HTTP(S) transport. Initial scheme/authority/port/userinfo/control-character rejection is additional hardening. Redirects require the same scheme, normalized hostname and effective port; changes and downgrades fail before the destination receives a request. Rejected responses close without draining untrusted bodies. Same-origin redirects retain urllib method semantics. Request validation remains inside collector/delivery/export error boundaries. The fixed OpenAI initial URL also receives redirect protection.

Standalone proof/readiness scripts retain independence from an installed package and reject all redirects, so another endpoint cannot satisfy the selected endpoint's proof. Runtime loopback/private URLs, operator-selected proxies, timeouts and custom TLS contexts remain supported. Trusted configuration/proxies and DNS behavior remain outside a network-sandbox guarantee. No private-address ban or credential grant was introduced.

Twelve transport tests pass normally and under optimized Python: GET/POST across 301/302/303/307/308 leave cross-origin receivers untouched; same-origin behavior, scheme/host/port/downgrade checks, malformed input rejection before I/O, response closure, proxy routing, HTTP error/loop behavior and all six collector/delivery/export caller contracts are exercised. TLS context forwarding is mocked; no TLS handshake qualification is claimed. Three standalone tests cover initial rejection, no redirect-target access and -O/-OO proof rejection before a receipt. The existing setup-plan no-network test also guards the new helper.

The two remaining B310 matches are synthetic loopback HTTP fixture calls. Their initial endpoints are created by the test itself; they were retained without suppression. Scanner silence at wrapper-based calls is not evidence of safety: regression tests and reviewed control flow support the result. Python documents urllib's configurable handlers and non-HTTP URL support in its [official reference](https://docs.python.org/3.11/library/urllib.request.html).

## Medium findings outside URL handling: 20

| Rule | Count | Reviewed disposition |
| --- | ---: | --- |
| B608 SQL construction | 16 | No injection defect established in these paths. Fifteen SQL sites interpolate fixed identifiers or identifiers from domain/column allowlists or trusted synthetic schema; data values use bound parameters. The dashboard line-159 match is HTML rendering, not SQL execution. |
| B102 exec | 3 | Test-only execution of trusted repository source/embedded observer code. Two in `test_pbs_native_verify_cache.py` and one in `test_review_regressions.py`; no external runtime input found. |
| B307 eval | 1 | `test_cycle_delivery_commands.py:115` evaluates a selected expression from trusted repository AST with synthetic test scope. Not a runtime user-input expression. |

SQL review included `api/status.py:188`, eight sites in `api/v1.py`, fixed migration column list in `migrate_notify_allow_mount.py:56`, literal export table/state pairs, literal notification table list, two allowlisted dashboard queries and one synthetic test-schema insertion. An attacker able to replace local source/schema is outside the claimed input boundary.

## Low findings: 173

| Rule | Count | Reviewed disposition |
| --- | ---: | --- |
| B101 assert | 68 | Real optimized-interpreter evidence issue: 24 live evaluator and 35 HTTP proof checks disappear under `-O`/`-OO`/`PYTHONOPTIMIZE`. One baseline mutation row-count guard also disappears. Six staging-smoke checks and two self-watch module self-checks are diagnostic assertions with the same optimization limitation. |
| B404 subprocess import | 32 | Imports alone do not establish command injection: 19 runtime, 3 operator scripts, 10 tests. Concrete calls reviewed under B603/B607. |
| B603 subprocess without shell=True | 49 | 22 runtime, 8 operator-script, 19 test call sites. Argument lists, trusted module commands/explicit operator-selected executables, pinned Git revisions or synthetic test commands; no remotely controlled shell command injection established. Trust assumptions below remain material. |
| B607 partial executable path | 11 | 3 runtime (`systemctl`, two `bash` loaders), 5 operator-script (`git`/`systemctl`), 3 test paths. Depends on trusted PATH; hardening opportunity, not an independently demonstrated lower-privilege exploit. |
| B110 except/pass | 10 | Eight best-effort rollback/close handlers preserve the original failure or cleanup semantics. One substantive diagnostic weakness remains: optional backup status-summary error swallowed. The hardware successful-exit invalid/missing JSON fallback has been fixed to fail closed. |
| B112 except/continue | 1 | Invalid/unreadable plugin TOML is silently skipped during freshness-threshold loading; default threshold remains. Diagnostic/configuration hardening opportunity. |
| B105 password string | 2 | False positives: `model_eval.py` report `pass=False`; synthetic test sentinel `private-token-value-do-not-emit`. No embedded real credential found in these two matches. |

### Confirmed optimized-interpreter defect and fixes

The live evaluator could return no failures for bad health with optimization enabled because its assertions were removed. It now rejects optimized execution at both `assert_case` and `run_suite`, before importing MCP, reading a suite or opening a connection. Normal assertions remain active under ordinary Python. This is deliberate fail-closed behavior, not scanner suppression.

Baseline adoption now uses an explicit row-count comparison raising `RuntimeError` inside its rollback-protected transaction. A synthetic SQLite `RAISE(IGNORE)` trigger reproduces a silent missing insert: normal, `-O` and `-OO` execution must roll back the entire batch and must not write an applied receipt.

The standalone HTTP proof rejects optimized execution before parsing arguments or making requests; -O/-OO regressions require nonzero exit and no receipt. The staging-smoke entry point now rejects optimized execution before creating temporary state. Two standalone self-watch module self-check assertions remain diagnostic limitations: run that self-check without optimization. They are not admission guards for remote input.

### Residual subprocess trust and availability limits

HA collector and notification delivery intentionally source an administrator-managed credential shell file using a constant `bash -c` script with the file path as a positional argument. This avoids interpolating the path into shell source, but the credential file is executable shell input; file ownership/permissions and PATH must remain trusted. No arbitrary untrusted file should be accepted as a credential source. Explicit operator-selected comparator/explainer/Python paths similarly execute the selected program by design. SSH collectors use explicit argument lists and strict host-key checking; configured usernames, hosts, keys and known-hosts files are administrator-controlled, not newly validated by this review.

Several cycle/helper subprocess calls lack Python-level timeouts. A hung child can stall a cycle; this is an availability hardening concern, not proof of injection. Systemd limits and child-specific timeouts were not exhaustively proven for every call here. Do not infer safety solely from absence of `shell=True`.

### Diagnostic limitations at the first follow-up commit

These two issues are addressed by the subsequent [status diagnostics follow-up](STATUS_DIAGNOSTICS_FOLLOWUP.md); the description below records the original finding, not the final behavior.

`api/status.py:863` can omit a backup summary after an unexpected parsing/summary error without exposing that error. `api/status.py:496` silently falls back when plugin threshold metadata cannot be read/parsed. These behaviors were confirmed by source inspection; fault-injection and downstream health-impact analysis remain follow-up work. Optional API diagnostic metadata is explicitly deferred in this bounded change; no new API representation was introduced. These findings do not establish that recovery was falsely recorded, and no incident or live collector state was changed.

### Confirmed hardware false-success defect and fix

The former `hardware/cycle.py:135–137` fallback converted a child exit 0 with empty/malformed output into `OK`/`no_json`. The main cycle then emitted `OK` with default zero incident counters and exited successfully, allowing systemd cycle-result recording to label the cycle successful. That was a false processing-success path, not demonstrated fabrication of incident recovery. The actual hardware processor normally emits valid JSON, so a broken/mismatched child was a required trigger.

The guard now requires the complete stdout to be one JSON object, `status=OK`, the actual producer identity `consumer=hardware_incident_processor`, and the producer's five nonnegative integer counters (`opened`, `escalated`, `recovered`, `processed`, `open_incidents`). Booleans do not count as integers. All four actual producer branches (no observations, already processed, bootstrap, processed observations) provide these fields. Invalid output raises before notification work or cycle-success emission. Observation rows recorded earlier in the cycle remain retained; this check does not claim to roll back already committed observations or a child's work.

## Focused validation

`python3 -m unittest discover -s tests -p test_optimized_acceptance.py`: 3 tests pass, covering six optimized live-entry subcases (`-O`, `-OO`, environment optimization across direct checks and suite entry), ordinary bad-health rejection, and three transactional rollback modes. `python3 -m unittest discover -s tests -p test_pve_baseline_adoption.py`: 7 existing tests pass, covering planning, backup/preservation, missing/duplicate/existing/stale resource rejection and database-error rollback.

`python3 -m unittest discover -s tests -p test_hardware_processor_result.py`: 6 tests pass: four valid producer variants; ten absent/malformed/non-object/extra-output cases; wrong/missing status/identity and 30 missing/invalid counter cases; nonzero exit despite successful JSON; main-cycle rejection before notifications/success emission; and three staging optimization preflights (`-O`, `-OO`, environment). `python3 -m unittest discover -s tests -p test_cycle_delivery_commands.py`: 3 existing tests pass, including execution of the actual packaged hardware processor against a fresh synthetic database. `python3 tests/staging_smoke.py`: PASS, 30 manifest entrypoints, 17 safe CLI calls, empty notification queue.

These checks use temporary synthetic databases and local Python subprocesses; no live host probes or state changes. The new source is unqualified until its applicable tests, review, packaging and candidate-specific qualification are completed. Frozen RC5 evidence applies to its original bytes, not these fixes. Hosted-client acceptance and the separate 1.1 routine-use gate remain distinct.

## Validation at first follow-up commit 95a3bc8

On October 11, 2026, the complete publication gate (which validates but does not publish) passed **297 tests** with ResourceWarning treated as errors, staging smoke (30 entrypoints, 17 safe CLI paths), compilation, and source privacy scanning (224 files). Environment: macOS arm64, Python 3.14.7. An independent reviewer passed 27 focused transport, acceptance, hardware and cycle tests and found no remaining blocker in the inspected diff after response-cleanup and exception-contract corrections. This is not a Debian/Python 3.11 deployment or hosted-client test.

The follow-up Bandit 1.9.4 scan of the same four directories on Python 3.14.7 covered 19,376 lines with zero scan errors: **0 high, 22 medium, 179 low**, exit 1. No findings were suppressed. Remaining medium findings are 16 SQL patterns, three test exec sites, one test eval site and two loopback test URL calls, with dispositions above. Low findings: 67 assert, 35 subprocess imports, 52 subprocess calls, 11 PATH-dependent calls, nine except/pass, one except/continue and four password-string matches. The two additional password matches are explicit synthetic test values. Added regression subprocesses account for increased import/call findings. Assertions protected by explicit optimized-execution refusal still appear in the scan; the two self-watch diagnostic assertions retain their documented limitation.

Static analysis is not clean. Residual API diagnostics, trusted PATH/configuration, child timeout coverage, and untested dependency/TLS/deployment behavior remain explicit limits. Changed runtime bytes require separate candidate versioning and exact-artifact lifecycle, security, client and sustained qualification; no old receipt is transferred and no new run, publication or deployment is authorized by this report.
