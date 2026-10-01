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

The 1.2 candidate includes read-only setup planning, honest domain/historical coverage, deterministic incident explanations, reproducible local/private hosted Investigator packaging and a bounded read-only connection check. These changes grant no action authority and enable no new monitoring domain.

Candidate completion requires:
- All correctness, lifecycle, notification retry, collector failure/freshness, missing evidence, unsupported-resource, pagination and authority cases pass.
- Fresh install/reboot, upgrade from stable, rollback/reupgrade, state/config preservation and invalid-wheel rejection pass against exact candidate bytes.
- Local client installation/cached-policy integrity, MCP connection/contract, and private hosted import/explicit-selection acceptance are separately retained.
- Expanded artifact privacy scans, dependency audit and static-analysis review are retained with their limits.
- A 72-hour consecutive evidence-backed disposable synthetic operation window is complete. Record configured fixture scope, cycle evidence, sample gaps, artifact hashes and injected failure/recovery separately. This proves fixture operation only; production routine-use qualification remains a separate gate.
- No unresolved correctness, privacy or authority defect remains.

Desktop activation, implicit selection and broader audience distribution are unsupported until separately tested. Public release/stable promotion requires the completion matrix to show PASS for supported scope. Time gates remain PENDING until actual evidence exists; a scheduled assessment is not a passed gate.
