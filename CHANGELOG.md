# Changelog

## 1.2.0.dev2 — In development

- Add deterministic incident explanations for opening/latest abnormal conditions, recovery references, missing evidence and conflicting lifecycle records; no root cause or current health inferred.
- Add read-only `rackmarshal setup-plan` guidance with fixed configuration key/file readiness results, no secret values and no target probes.
- Identify enabled/disabled domain selection on dashboard and detail coverage; preserve disabled-domain records as historical evidence and explicitly state unsupported monitoring coverage.
- External tester feedback is additive; internal evidence and exact-artifact gates decide release promotion.


## 1.1.0rc1 — 2026-09-30 (tester preview)

### Added
- Stable read-only API v1 and eleven goal-oriented MCP tools.
- Deterministic incident timelines/evidence bundles with typed references, explicit authority/provenance, pagination, and recovery history.
- Incident dashboard/detail pages with lifecycle timestamps, counts, evidence links, and observation freshness distinct from incident state.
- Durable exact-unit cycle result recording through systemd drop-ins.
- Portable read-only Investigator policy and optional edge clients/evaluations; core remains usable without AI.
- Pinned package promotion and bounded operator-only PVE baseline adoption tools.
- Standalone PBS verification-cache observer source with bounded task-history selection and explicit site arguments; failed guest execution remains UNKNOWN.

### Fixed
- Dashboard completeness beyond 200 incident rows per domain.
- PVE lifecycle evidence compaction when event detection trails observation time.
- Missing PBS weekly-job visibility within the previous 100-task window; the helper now searches up to 1000 tasks and retains UNKNOWN when unmatched.

### Boundaries
- No infrastructure-write MCP tools or automatic incident closure.
- PBS helper and operator tools require explicit site setup; the base installer does not deploy them automatically.
- Optional MCP dependencies and hosted connection/policy setup are separate from the base installer.
- Private workspace bindings and production operational evidence are excluded from public assets.
- Combined cloud plugin installation is not yet qualified. A generic local plugin is included; hosted users configure their own private connection and policy.
- Downloads, network monitoring, and storage capacity/growth collectors remain deferred.


## 1.0.0

- Added the supported `rackmarshal` CLI with version, domain listing, configuration validation, migration, and diagnostic commands.
- Added explicit enabled-domain scheduling with generic hardened systemd service/timer templates.
- Added automated unit, comparator, notification failure, installer-contract, migration, smoke, and publication gates.
- Added GitHub Actions CI, CodeQL, Dependabot, and reproducible release-build workflow.
- Added deterministic installer-bundle construction and strengthened preflight validation.


All notable RackMarshal changes intended for public releases will be documented here.

RackMarshal 1.0.0 is the first stable public release.

## [Unreleased]

### Added
- RackMarshal package structure extracted into a site-independent staging tree.
- SQLite schema construction through 12 ordered migrations.
- Domain manifests and processing components for PVE, ZFS, backup/PBS, Home Assistant, hardware, and mount monitoring.
- Local status API with `/health` and `/status` endpoints.
- Notification queue/service and timer packaging.
- Apache License 2.0 repository and package metadata.
- Debian/systemd reference installer and uninstall/purge workflow.
- Public installation, configuration, upgrade, uninstall, security, and contribution documentation.

### Verified during pre-release engineering
- fresh database construction from packaged migrations
- package import and plugin-entrypoint validation
- installation from built artifacts on a disposable clean Debian 12 host
- unprivileged service account and filesystem permissions
- systemd startup and health verification
- idempotent reinstall and migration preservation
- reboot recovery
- standard uninstall preserving configuration/state
- reinstall using preserved state
- destructive purge path
- whole-release publication/security scanning

### Changed
- remaining legacy project identifiers in staged Python and migration content were renamed for RackMarshal.

The pre-release engineering record above documents the qualification work that led to the 1.0.0 release.


## Development — 2026-09-30

- Improve deterministic incident dashboard/detail presentation with domain open
  counts, exact lifecycle timestamps, occurrence/repeat counts, context, and
  clearer historical recovery, evidence, provenance, and authority language.
- Fix dashboard completeness beyond 200 incident records per domain.
- Add narrative regressions, repeatable real-data HTTP proof, and a prepared
  ChatGPT Business Investigator connection guide; no workspace changes made.
