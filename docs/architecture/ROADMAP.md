# RackMarshal Architecture Roadmap

Status: **ACTIVE ROADMAP**
Updated: 2026-10-01
Basis: September 29 architecture decisions, September 30 recorded qualification, and user-approved priority revision.

## Long-term purpose

RackMarshal is an open-source, local-first operational truth layer for heterogeneous self-hosted infrastructure, humans, and agents. Core observes state, detects divergence, preserves incident evidence, and independently records recovery. Core remains usable without AI; API and MCP contracts remain provider-neutral.

AI may investigate, explain, correlate, and recommend within its granted capabilities. Its synthesis is ADVISORY. Read authority and action authority remain separate. No agent may invent evidence or declare recovery without an independent RackMarshal observation.

## Demonstrated foundation and qualification limits

The September 29 roadmap's API, read-only MCP, provenance, and investigative-agent milestones now have implemented and tested evidence. The six-domain production deployment, incident dashboard/detail pages, collection freshness presentation, current-unit cycle recording, evidence compaction, PBS history visibility fix, and scoped PVE baseline adoption are recorded in SOURCE_OF_TRUTH.md.

The private ChatGPT Business Investigator has eleven read tools and passed explicit-skill acceptance for incident lifecycle, evidence references, facts/advisory separation, uncertainty, bounded summaries, and write refusal. User-reported tests of unmonitored resources support normal private use. Raw workspace tool arguments/results, implicit activation, broader audience controls and implicit activation remain separate qualification items. Exact RC1 disposable install/upgrade/rollback and private combined cloud packaging have now passed within their recorded scopes.

These are demonstrated capabilities in the qualified environment, not new public release declarations or universal deployment guarantees. Milestones below express sequencing; release version numbers require their own gates.

## 1.1 qualification and 1.2 development

1.1 RC1 is published and download-verified; 1.0.0 remains stable. Apply [internal release acceptance](RELEASE_ACCEPTANCE.md) before promotion. Continue 1.2 development in parallel: guided setup, explicit monitoring coverage, then clearer deterministic investigation summaries. Setup/coverage and deterministic incident explanation increments implemented on development/1.2-setup-coverage, development version 1.2.0.dev2; not deployed to production or released.

## Revised priorities and completion evidence

### 1. Sustained reliability and evidence quality — NOW

Use the private Investigator routinely with explicit skill selection. Verify naturally occurring incident/recovery paths, collection failures, freshness, notification behavior, and evidence completeness. Treat missing, stale, metadata-only, and paginated evidence explicitly.

Maintain acceptance cases for unsupported resources and coverage questions. Answers must distinguish monitored, unmonitored, unknown, and historical information without fabricating observations or causes. Complete pagination when claiming an exhaustive inventory.

Gate: a documented observation period and representative failure/recovery cases with retained evidence, declared gaps, and no unresolved correctness or authority violations. Passing a one-time acceptance suite alone does not complete this milestone.

### 2. Reproducible product experience — ACTIVE, WITHOUT EXTERNAL DEPENDENCY

Qualify the current experience on an independent disposable installation: install, configure, connect, investigate, upgrade, preserve history, and roll back. Reconcile public documentation and supported platform boundaries against exact final artifacts. Qualify policy binding and access/audience controls; independently test any combined cloud package or implicit activation before advertising it.

Continue internal qualification and 1.2 development without waiting for others. External tester feedback supplements evidence and is not a release prerequisite. Recruit hands-on testers to find installation and operational failures. Broader ecosystem/creator outreach follows reproducible installation and mature integrations; broad launch follows product qualification.

Gate: installer-only acceptance, upgrade/rollback and security/publication checks on the exact artifacts, plus evidence-backed internal routine-use qualification. Independent feedback is additive. Existing historical gates remain evidence only for their tested scope.

### 3. Deliberate monitoring expansion — DEFERRED

Future additions: downloads, network monitoring, and storage capacity/usage/growth. Capacity planning should account for future growth and long-term architecture.

For each addition define resource identity, expected state, observation source/time/freshness, thresholds and persistence, maintenance/disabled behavior, incident opening criteria, supporting evidence, and independent recovery criteria. Missing telemetry is distinct from observed resource failure. Demonstrate the full observation/event/incident/recovery path before enabling a domain in production.

Gate: reviewed scope and policies, disposable failure/recovery proof, qualified packaging, and a reversible production promotion. This roadmap does not enable collectors or change incident policies.

### 4. Accountability and policy foundations — BEFORE ACTION AUTHORITY

Move the agent audit ledger ahead of, or into, the first controlled-action milestone. Persist requester/runtime identity, capability and parameters, evidence used, policy decision, approval identity where required, execution result, timestamps, and independent verification outcome. Minimize and sanitize retained data.

Gate: durable audit records and tested deny/approval paths exist before the first action capability is granted. An accepted or executed action is not proof of recovery.

### 5. Bounded operational actions — LATER

Introduce capabilities incrementally: scoped diagnostic/collection requests first, then selected reversible operations under explicit policy. Use the existing C0-C4 security model, deny-by-default evaluation, approval rules, bounded scope, and rollback/verification requirements. Keep Investigator read authority separate from operator execution.

Gate: disposable action, denial, approval, failure, rollback, and verification tests pass; audit evidence is retained; each production grant is explicitly authorized. No action capability or permission expansion is enabled by this roadmap.

### 6. Provider independence and optional specialist agents — LONG TERM

Preserve provider-neutral contracts throughout all phases. Qualify additional agent runtimes against the same evidence and authority acceptance cases before claiming demonstrated portability. Introduce optional specialist or multiple agents only after reliable single-agent investigation and controlled actions are proven, with shared truth, scoped capabilities, and traceable handoffs.

Gate: cross-runtime acceptance and demonstrated operational benefit. Multiple agents are optional and are not a prerequisite for a useful core product.

## Review cadence

Reevaluate monthly, on the last morning of each month in America/New_York, beginning October 31, 2026. Also reevaluate during an active work session after a major release, significant evidence/authority defect, new deployment, or proposed action-capability change. Only the monthly review is scheduled; milestone-triggered reviews are a workflow practice.

Read this roadmap and current SOURCE_OF_TRUTH.md before reviewing. Compare verified progress with each gate, identify stale assumptions and missing evidence, and recommend whether to continue, reorder, or defer work. Keep reviews concise and use the smallest sufficient read-only evidence set. Recommend changes for Michael to review; do not automatically expand scope, grant authority, deploy code, or publish the workspace experience.

## Evidence sources

- SOURCE_OF_TRUTH.md — authoritative implementation and qualification checkpoints.
- AGENT_ARCHITECTURE.md and CORE_PRINCIPLES.md — architecture and deterministic authority.
- SECURITY_MODEL.md — capability and audit requirements.
- evals/results/business-policy-acceptance-20260930.json — scoped workspace acceptance receipt.
