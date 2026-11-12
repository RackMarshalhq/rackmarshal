# Changelog

## 1.3.0rc2 — Release candidate (release gate pending)

Fixes and friendlier tooling since 1.3.0rc1, including the first (unqualified) 1.3.x upgrade command. 1.3 still installs fresh only; upgrading is for testers who accept that it has not been qualified on a real system beyond one disposable-container trial.

- **Fix: backup ledger rejected five of its eight resource types on a fresh install.** Migration `004` limited `backup_events` and `backup_incidents` to three resource types, so events for Time Machine, phone, Messages, host verification and rsync file-backups were silently dropped and incident processing then failed with "missing backup event". New migration `011_backup_resource_types` rebuilds both tables with all eight types, keeping every row, id and index; `004` is unchanged so existing checksums and `carry-baselines.py` still work. A site that already has the wider tables is unaffected in behaviour. The backup domain is still documented as unsupported for new installs until it is proven on a fresh install.
- **Fix: secondary check alerted every morning while verification was still running.** A freshly copied snapshot has no verification record until the secondary server verifies it, so the secondary coverage check reported "missing_invalid_or_source_reference" from the time of the copy until verification finished (about 2.5 hours on one site) every day. A copy that has not been verified on the secondary yet is now treated as pending while it is younger than `BACKUP_SECONDARY_SOURCE_LAG_GRACE_HOURS` (default 8): either no verification record at all, or the "ok" record a copy brings from its source datastore (a verify task of another datastore; this is what a sync actually produces). A recorded failure or any other state, a malformed reference, and an unverified copy older than the grace still report.
- **`rackmarshal upgrade` (new, unqualified).** One command for a 1.3.x to 1.3.y upgrade: it runs the `upgrade-plan` checks against the wheel in an extracted installer bundle and shows the exact command; only `--apply --note "why"` as root runs that bundle's `scripts/lifecycle.py` (backup, pause, switch, health proof, automatic rollback). It refuses anything the plan refuses, releases with database changes, and a missing note or non-root run. Not qualified on a real machine; UPGRADE.md says not to use `--apply` on a system you depend on, and 1.3 remains fresh-install only.
- **Lifecycle script: health proof with automatic rollback (internal tooling).** The transaction engine gained an optional verification step after the workloads resume; if it fails, the workloads are held again (RECOVERY_REQUIRED, never COMMITTED) and the old version can be restored with every newer record kept. `scripts/lifecycle.py upgrade` now refuses to start unless `rackmarshal doctor` is clean on the installed version, and after the switch waits (`--verify-timeout`, default 1800 s) for one successful run of every enabled check and a clean doctor; on failure it rolls back by itself. Crash-interruption tests cover the new step. Not exposed through `rackmarshal`, not run on a real machine; 1.3 remains fresh-install only.
- **Lifecycle script: standard installs and leftover bytecode (internal tooling).** The transaction engine only recognised the status, notify and domain units, so it refused every normal install, which also has `rackmarshal-db-snapshot` and `rackmarshal-observation-prune` (service and timer each). Those are now held and restored like the other timers while maintenance runs, but only when installed; any other unknown unit is still refused. Separately, running a `rackmarshal` command as root leaves regenerable `__pycache__/*.pyc` files in the install folder, which the exact-file check rejected; the script now deletes only plain `.pyc` files in `__pycache__` folders inside the installed package before that check, and anything else found there still fails it. Found by a trial in a disposable container. Not exposed through `rackmarshal`; 1.3 remains fresh-install only.
- **Upgrade command wording.** The `rackmarshal upgrade` dry run still said the apply step was not available yet (text carried over from `upgrade-plan`). It now says the upgrade can be applied and that the check itself changed nothing; `upgrade-plan` says it only checks.
- **Lifecycle script: automatic undo no longer trips on an empty leftover folder.** When the health check failed, the script looked for the transaction to roll back by reading every transaction folder, and stopped with a file-not-found error if an earlier refused run had left an empty one, leaving the new version installed with checks paused. It now skips folders that have no journal. Found by the second disposable-container trial.
- **Lifecycle script accepts any 1.3.x predecessor (internal tooling).** `scripts/lifecycle.py` was pinned to one pair of private development builds. It now takes the predecessor wheel plus `--previous-sha256` (copied from the release page), requires the bundle's release to be newer and in the 1.3 series, and still refuses database changes, changed units, custom layouts and unfinished transactions. It is not exposed through `rackmarshal`, has not been run on a real machine, and 1.3 remains fresh-install only.
- **`rackmarshal upgrade-plan` (new, read-only).** Phase 1 of a 1.3.x-only upgrade. Given the new release's wheel and its SHA256SUMS file (or a checksum you copied separately), it checks that the installed files still match the installed release (a hand patch is named and refused), that the wheel matches its checksum and its own RECORD, that both versions are 1.3.x with the new one newer, and whether the database would need changing. It installs and changes nothing; the apply step with automatic undo is not part of this change. 1.3 remains fresh-install only.
- **`rackmarshal doctor` (new).** A read-only first-run check in plain words: settings file, database integrity, DNS (including the Tailscale-only resolver a container inherits when you give it a static IP), credential file permissions, scheduled timers, the last run of each domain, and the status page. Each result is PASS, WARN or FAIL with what to do next. It reads no credentials and changes nothing.
- **`rackmarshal retire-guest` (new).** `rackmarshal retire-guest 123` shows a plan for forgetting a guest you deleted from Proxmox; it finds the fresh observation itself, so no observation number is needed. `--apply --note "why"` (root) saves a database copy first and refuses any guest Proxmox still lists. `scripts/retire-pve-baseline.py` remains for scripted use.
- **Alerts explain themselves.** Opened and recovered alerts now start with "What happened", "Does it matter" and "What to do" (fixed wording, nothing guessed), followed by the original technical details unchanged. The secondary-copy checks have their own wording.
- **Fix: "new guest" and "new job" backup alerts never closed.** A backup incident of type NEW recovered only if the same item later matched a baseline, so deleting an unlisted guest left its alert open forever. It now recovers as soon as the item is no longer reported; MISSING incidents are unaffected.
- **Fix: database-change rehearsal refused every real migration.** The rehearsal required every row of every old table to stay identical, but the `metadata` table holds version markers that each migration adds or bumps (migration 011 sets `backup_ledger_schema`), so the real upgrade from 1.3.0rc1 to rc2 was refused with "rows in table metadata would change". Version markers may now be added or changed; none may be removed. Found by the disposable-container trial. 1.3 remains fresh-install only.
- **`rackmarshal upgrade` can apply releases with database changes (step 3 of 3, unqualified).** The bundle's lifecycle script no longer refuses a release because it adds migrations. It requires the new ones to come after every applied one and never to rewrite an earlier one, rehearses them on the verified backup of the quiesced database, and proves the program it could go back to still works on the changed database: the full synthetic ZFS suite on a fixture with the new changes applied, and read-only checks against a copy of the real data. After the switch the changes run in one all-or-nothing step that must match the rehearsal. Undo (also the automatic undo after a failed health proof) restores the old program, re-runs that proof, and keeps the changed database and all newer records. `rackmarshal upgrade-plan` and `upgrade` report such releases as ready with their database changes. Also fixed: `uninstall.sh` now removes leftover lifecycle maintenance guards (`99-lifecycle-maintenance.conf`) so a reinstall after an interrupted upgrade is not blocked. Not run on a real machine; 1.3 remains fresh-install only.
- **Lifecycle engine can apply database changes (internal step 2 of 3).** The transaction engine gained two journaled phases, MIGRATE_INTENT and MIGRATED, after the new code is switched in and before acceptance. The release's new migrations (checksummed, strictly after every applied one) run on the live database in a single SQLite transaction, and the result must match the layout rehearsed by `upgrade-plan` or nothing is kept. Undo restores the old code and keeps the migrated database and every newer record (the database is never rewound); it accepts the database only if it is exactly the pre-upgrade layout or exactly the rehearsed one, so a crash at any phase recovers. Tests interrupt every phase, including real process exits at both migration phases. Not reachable from `rackmarshal upgrade` or `scripts/lifecycle.py` yet (they still refuse database changes), and the check that the old program runs on the changed database comes with the command wiring. 1.3 remains fresh-install only.
- **`rackmarshal upgrade-plan` rehearses database changes (internal step 1 of 3).** When a release adds database changes, the plan now checks they only come after the newest applied one, then applies them all-or-nothing to a private copy of your database and confirms that every table, column and row you had is kept (a migration may add or rebuild tables but not lose data). The result is a new status, READY_WITH_DATABASE_CHANGE, with the expected layout; your real database is never touched. `rackmarshal upgrade --apply` still refuses such releases until the engine support lands. 1.3 remains fresh-install only.

- Version 1.3.0rc2 has not completed the release gate. The exact-artifact result will be stated in the release notes.

## 1.3.0rc1 — Release candidate (release gate pending)

RackMarshal 1.2 was never released. 1.3 includes all of the 1.2.0 candidate work listed below.

- **ZFS permanent errors.** A pool that is online but reports permanent data errors now opens an incident, and an incident recovers only on recorded clean evidence. A missing error count is recorded as unknown, not zero. RackMarshal 1.0.0 and 1.1.0 RC1 record such a pool as a counter change that opens no incident and can close an open incident as recovered; they also record a missing error count as zero.
- **Self-watch fixed and shipped as an optional unit.** It watched unit names from the old layout (`rackmarshal-status-api.service`, `rackmarshal-*-cycle.timer`) and every domain regardless of `ENABLED_DOMAINS`, so a clean 1.3 install would have opened 14 false incidents. It now watches `rackmarshal-status.service`, the timer and service of each enabled domain, and its own timer if installed, and only the enabled domains' data. `rackmarshal-self-watch.service` and `.timer` ship under `packaging/systemd/optional/` (not enabled by the installer). The `self_watch.units` and `self_watch.freshness` keys in `/status` now list only those. See CONFIGURATION.md.
- **Credential file permissions.** `validate-config` rejected the documented mode 0640 (owner root, group `rackmarshal`) for `PVE_API_ENV`, `PBS_API_ENV` and `HA_CREDENTIAL_FILE`. Those three may now be group-readable; group-write and any access for others are still rejected, and SSH keys, known-hosts and certificate files still require owner-only access. The Quickstart now names `HA_CREDENTIAL_FILE`, and INSTALL.md lists `sudo` among the packages to install.
- **Baseline carry-over tool.** `scripts/carry-baselines.py` no longer refuses a 1.0.0 site whose unrelated migration files were edited. It now requires identical checksums only for the migrations that create the copied tables (`001`-`004`), still refuses an old database that is newer than the new one, and still compares every copied table in full.
- **Proxmox and backup incident processors start themselves.** On a fresh install they stopped with "incident processing ledger has no checkpoint" and nothing in the documents or tools could create the checkpoint. The first run on an empty ledger now writes a starting marker (at the newest earlier observation, if any), refuses when incidents exist without a ledger, and keeps strict ordering afterwards. The Proxmox section of CONFIGURATION.md also now states that `PVE_API_URL` must end in `/api2/json` and that the token needs the `PVEAuditor` role.
- **Optional MCP service.** `rackmarshal-mcp.service` (loopback only, hardened, not enabled by the installer) runs the read-only Investigator MCP server; install steps are in CONFIGURATION.md. The secure tunnel to a hosted assistant stays your own private setup.
- **Optional evidence-export timer.** `rackmarshal-evidence-export.service` and `.timer` (daily, 35 days) ship under `packaging/systemd/optional/`, are bundled and removed by the uninstaller, and are documented in CONFIGURATION.md. The installer does not enable them.
- **Optional status-page firewall.** `scripts/status-acl.py` prints an nftables rule file that limits the status page to the callers you list, with an optional `rackmarshal-status-acl.service` (not enabled by the installer). See CONFIGURATION.md.
- **Observation prune is now installed.** The prune module shipped without a timer, so a fresh install never pruned and the database grew without limit. The installer now enables `rackmarshal-observation-prune.timer` (weekly, 35 days; see CONFIGURATION.md).
- **Backup SSH probe documented as a private extension.** The checks that read the SSH store probe are documented as unsupported (the program that produces the probe is not part of RackMarshal), and the rsync file-backups check now runs only when `BACKUP_RSYNC_FILEBACKUPS_CHECK=true`. If you relied on it, set that value.
- **Backup baseline tool.** `scripts/adopt-backup-baseline.py` (new, in the installer bundle) records one backup job and the guests you name from a fresh observation; plan first, `--apply` to write, refuses bad states and never overwrites. The backup domain is still not supported for new installs until it is proven on a fresh install.
- **Optional secondary PBS check.** The backup domain can now check a second Proxmox Backup Server datastore (`BACKUP_SECONDARY_STORE`; off by default; read-only; limits are settings). Coverage and capacity are separate results, and a failure never stops primary collection. The backup domain itself is still not supported for new installs (no baseline tool yet).
- **Workflow actions updated.** CI, CodeQL, quickstart and release-build workflows now use `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7` and `github/codeql-action@v4`. `actions/download-artifact` stays at v4. No change to the installed product.
- **Retire the baseline of a deleted guest.** Deleting a guest in Proxmox left its baseline row behind, so RackMarshal reported it as MISSING forever and nothing could clear it. `scripts/retire-pve-baseline.py` (new, in the installer bundle) removes the row: plan first, `--apply` to write, refuses a guest that still exists, writes a database copy first and never touches incidents or events. See PVE_BASELINE_ADOPTION.md.
- **MCP install instructions fixed.** The 1.3 environment has no pip, so the documented `/opt/rackmarshal/venv/bin/pip install` could not work. CONFIGURATION.md and the Investigator installation guide now show how to install the `mcp` package with a separate pip pointed at the environment.
- **Documentation fixes.** CONFIGURATION.md now says `PBS_API_URL` has no path (the collector adds `/api2/json`), that the URL's name must match the certificate, and that events are kept by the observation prune. It no longer says 1.3 does not prune.
- **Fresh-install-only installer.** Offline: no `apt`, `pip` or network; unmodified pinned PyPA installer 1.1.0; pip-less virtual environment; refuses any existing installation, account or unit. There is no in-place upgrade in 1.3 (see UPGRADE.md).
- **Database snapshots.** A new daily timer, `rackmarshal-db-snapshot.timer`, writes an integrity-checked copy of the state database to `/var/lib/rackmarshal/db-snapshots/` (7 kept by default, `state.db.latest` for the newest). It refuses to run when the disk is nearly full. The installer runs one snapshot as part of its self-check, and the uninstaller removes the units. A new test now fails if any packaged service points at a Python module that does not exist.
- **Baseline adoption.** `scripts/adopt-zfs-baseline.py` and `scripts/adopt-ha-baseline.py` (both new) and `scripts/adopt-pve-baseline.py` are now in the installer bundle. There is no backup baseline tool, so the `backup` domain is documented as not supported for new installations in 1.3. Baselines were previously only creatable by editing the database by hand. Both tools are insert-only, print a plan before writing, and back up the database first. CONFIGURATION.md corrects how to enable a domain after installation; the installer cannot be run a second time.
- **Soak kit.** `qualification/soak/` and `SOAK.md` (new; not part of the installer bundle) run a 24-hour soak of an installed RackMarshal on a disposable container: one launcher that refuses wrong flags, umask, hostname or target, eight checks every five minutes, a hash-chained ledger, one recorded retry per sample, and a permanent stop on failure. It uses synthetic data only.
- **Documentation that is tested.** The README is rewritten for newcomers, with `docs/QUICKSTART.md`, `TESTING.md` and issue templates. `scripts/check-docs.py` fails CI when the docs link to a missing file or heading, show a CLI command or domain that does not exist, or use an undocumented configuration key. A new `Quickstart` workflow installs the real bundle on a fresh runner with systemd, checks it is healthy with no incidents and has a valid database snapshot, takes two soak samples, and uninstalls.
- **Release gate profile for installer release candidates.** `Release Build` accepts `gate_scope: installer-rc`, which accepts the 24-hour installer soak in place of the 72-hour synthetic window and requires no MCP client activation claim. It applies to release candidates only; the default and stable scopes are unchanged.
- **Release workflow.** `Release Build` can now also create a DRAFT GitHub release from the qualified assets when given an existing tag. It still runs only after the qualification gate; pushing a tag alone builds nothing.
- **Known limitation: Ubuntu.** The installer refuses a group-writable parent folder, and stock Ubuntu's `/var/log` is `root:syslog 0775`, so 1.3 does not install on stock Ubuntu. Debian 12 is the only qualified platform; documentation now says so.
- **Observation prune.** New `python -m rackmarshal.maintenance.prune` deletes observation rows older than 35 days (`RACKMARSHAL_OBSERVATION_RETAIN_DAYS`, minimum 7) in batches of 500, together with their per-observation processing bookkeeping rows. Rows that events, incidents or baselines refer to are kept, as is each processor's checkpoint (its highest processed observation) and the newest two rows of each table. `--dry-run` shows what it would delete. The database file does not shrink, but growth levels off at about the retention window. It is not scheduled by the installer.
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
