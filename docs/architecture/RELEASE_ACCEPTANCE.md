# Internal release acceptance

External feedback is useful evidence, not a required approval or a reason to stop development. Release decisions depend on retained internal evidence for the exact artifact hashes.

## 1.1 stable promotion

RC1 already has exact-artifact installation/reboot, stable upgrade/rollback/reupgrade, state/configuration preservation, invalid-wheel rejection, read-only MCP positive/negative cases, CI and privacy checks. Published downloads were independently downloaded and byte/checksum verified. These gates apply to RC1 only; any changed artifacts require fresh qualification.

Before stable promotion:

- Retain at least 72 consecutive hours of routine-use evidence, covering repeated configured collection cycles. Record the actual start/end, enabled domains, freshness policy, failures and evidence gaps. Elapsed wall time alone does not prove successful collection. Longer cadence policies require explicit coverage limits.
- Require representative deterministic failure/recovery, notification retry, collector failure, missing/stale observations, unsupported resource, pagination and authority-denial cases. Use synthetic fixtures and disposable systems for deliberate failures. Never inject production faults to satisfy a gate.
- Require zero unresolved evidence correctness, history-loss, credential disclosure or authority violations. Existing resource incidents may remain open; a product promotion is not a resource recovery claim.
- Verify supported install/upgrade/rollback paths against the exact stable candidate; disclose security audit skips and reviewed findings. Recheck published checksums and stable/preview labels.
- Keep hosted/private package acceptance distinct from generic/public package acceptance. An unqualified client or activation mode remains explicitly unsupported; broaden support only after its own tests.

Qualification records must label PASS, FAIL, PENDING and scope limits. The 72-hour routine-use gate is PENDING until an evidence-backed window is recorded. This document does not automatically schedule work, deploy or promote a release.

## 1.2 development

Advance in parallel with 1.1 qualification: guided setup and explicit domain/resource coverage first; improve deterministic incident summaries and missing-evidence explanations next. Investigator remains read-only. Downloads, network and storage usage remain deferred until a separately reviewed observation/incident/recovery policy and disposable proof exists.

The first increment is `setup-plan` plus enabled/disabled/historical coverage presentation. It changes no collector or incident policy, writes no setup configuration and starts no services. Development version 1.2.0.dev1 is not a published release.
