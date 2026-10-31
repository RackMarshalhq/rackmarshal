# Changelog

## 1.3.0rc1 — Release candidate (release gate pending)

RackMarshal 1.2 was never released. 1.3 includes all of the 1.2.0 candidate work listed below.

- **ZFS permanent errors.** A pool that is online but reports permanent data errors now opens an incident, and an incident recovers only on recorded clean evidence. A missing error count is recorded as unknown, not zero. RackMarshal 1.0.0 and 1.1.0 RC1 record such a pool as a counter change that opens no incident and can close an open incident as recovered; they also record a missing error count as zero.
- **Fresh-install-only installer.** Offline: no `apt`, `pip` or network; unmodified pinned PyPA installer 1.1.0; pip-less virtual environment; refuses any existing installation, account or unit. There is no in-place upgrade in 1.3 (see UPGRADE.md).
- **Database snapshots.** A new daily timer, `rackmarshal-db-snapshot.timer`, writes an integrity-checked copy of the state database to `/var/lib/rackmarshal/db-snapshots/` (7 kept by default, `state.db.latest` for the newest). It refuses to run when the disk is nearly full. The installer runs one snapshot as part of its self-check, and the uninstaller removes the units. A new test now fails if any packaged service points at a Python module that does not exist.
- **Baseline adoption.** `scripts/adopt-zfs-baseline.py` and `scripts/adopt-ha-baseline.py` (both new) and `scripts/adopt-pve-baseline.py` are now in the installer bundle. There is no backup baseline tool, so the `backup` domain is documented as not supported for new installations in 1.3. Baselines were previously only creatable by editing the database by hand. Both tools are insert-only, print a plan before writing, and back up the database first. CONFIGURATION.md corrects how to enable a domain after installation; the installer cannot be run a second time.
- **Soak kit.** `qualification/soak/` and `SOAK.md` (new; not part of the installer bundle) run a 24-hour soak of an installed RackMarshal on a disposable container: one launcher that refuses wrong flags, umask, hostname or target, eight checks every five minutes, a hash-chained ledger, one recorded retry per sample, and a permanent stop on failure. It uses synthetic data only.
- **Setup guidance.** `rackmarshal setup-plan` reports missing configuration key names and credential-file readiness without writing anything.
- **Fix:** `rackmarshal diagnostic` with a missing or invalid configuration now prints a JSON `FAIL` result and exits 2 instead of ending with a traceback.
- **Internal:** the command-line code was rewritten for readability and its exact output is pinned by a test; tests no longer depend on the machine's umask; CI runs the suite as a normal user and as root.
- Version 1.3.0rc1 has not completed the release gate. The exact-artifact result will be stated in the release notes.

## 1.2.0rc5 — Local health-policy fix (not published)

- Require current get_health and get_status evidence for RackMarshal health questions in the runtime policy, packaged skill and deterministic health plan.
- Explain partial/unverified results, collection/freshness gaps and response-versus-observation timestamps without granting action authority.
- Verify health-policy parity across local and private hosted packages. Existing acceptance requirements remain unchanged; live client acceptance is pending.
- Frozen rc4 artifacts and its independent synthetic window remain unchanged. Changed rc5 bytes require their own qualification.

## 1.2.0rc4 — Local review candidate (not published)

- Gate candidate upload on exact source/artifact-bound qualification receipts and scan final assets before checksums; synthetic operation and production routine-use gates remain separate.
- Inspect nested and renamed compressed assets with bounded expansion; restrict scanner exemptions to exact reviewed declaration lines.
- Compare non-PVE material-change bounds by timezone-aware instants and expose timestamp gaps.
- Distinguish missing recovery time from no recorded recovery and historical recovery from current resource health.
- Changed bytes require new applicable qualification. Frozen earlier candidates are unchanged.

## 1.2.0rc3 — Local qualification candidate (not published)

- Integrate setup safety regression coverage and deterministic health acceptance fixtures.
- Require the exact eleven-entry MCP tool contract, rejecting duplicate names.
- Strengthen source/artifact privacy checks for renamed databases and archives, links, literal member paths, and public website attribution boundaries.
- Retain public-tree privacy cleanup and generic provider-neutral packaging.
- Fresh exact-artifact installation, lifecycle, security, client, and sustained synthetic qualification remain required; rc2 evidence is not transferred.

## 1.2.0rc2 — Qualification candidate (not published)

- Prevent mount recovery from missing/unknown observation rows; require an explicit healthy mount result and retain accurate OPEN counts.
- Add deterministic incident explanations for opening/latest abnormal conditions, recovery references, missing evidence and conflicting lifecycle records; no root cause or current health inferred.
- Add read-only `rackmarshal setup-plan` guidance with fixed configuration key/file readiness results, no secret values and no target probes.
- Identify enabled/disabled domain selection on dashboard and detail coverage; preserve disabled-domain records as historical evidence and explicitly state unsupported monitoring coverage.
- Add deterministic local marketplace/private hosted package construction, synchronized metadata and explicit private-binding isolation.
- Add bounded read-only Investigator connection/authority checks with sanitized failure reasons.
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

## 1.2.0rc6.dev1 (private, not release-qualified)

- Add pinned offline pip bootstrap with pip-less venv creation, input validation, isolated execution and installed inventory verification.
- Refuse existing installations and missing prerequisites before persistent changes.
- Retain upstream licenses/provenance and narrowly bind public CA privacy exceptions to exact hashes.
- Canonicalize installer and source archive permissions independent of checkout modes.
- Mac development tests do not satisfy Linux/systemd release acceptance.

## 1.2.0rc6.dev2 (private, not release-qualified)

- Replace pip bootstrap with unmodified PyPA installer 1.1.0 and full RECORD validation; install only RackMarshal into a pip-less venv.
- Remove bundled pip, its vendored dependencies and related privacy exceptions.
- Preserve ownership, integrity, permission and existing-install refusal boundaries. Cloud foreign-root ownership remains unsupported; genuine Debian root qualification is pending.

## 1.2.0rc6.dev3 (private, not release-qualified)

- Add a source-bound same-schema lifecycle CLI for the pinned corrected dev2 predecessor, durable recovery/rollback journals, persistent systemd maintenance guards and exact inventory authorization.
- Require synthetic permanent-error/unknown-evidence semantics before accepting either runtime. Refuse legacy stable rollback despite schema equality.
- Preserve newer database contents and protected configuration/credentials across rollback; generate staged launchers for the final path. Exact unchanged units only; Linux lifecycle and release gates remain pending.
