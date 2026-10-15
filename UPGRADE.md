# Private lifecycle qualification

Version 1.2.0rc6.dev3 implements a restricted, same-schema private qualification path: exact corrected dev2 → dev3 → dev2 → dev3. It is not a public support promise or a completed Linux qualification. The fresh installer refuses existing installations and cannot be used to upgrade or reinstall preserved state.

The predecessor is rackmarshal-1.2.0rc6.dev2-py3-none-any.whl, SHA-256 `137663acf2bd799b606c2a38db15b646d1a4649417f5c5a697a306afcfe725a5`. The candidate requires a complete source-bound installer bundle, matching installed wheel bytes and RECORD, unchanged SQL migrations and ledger, exact unchanged supplied core units, standard paths, the existing service account and loopback status endpoint. Unknown/custom/optional services, altered units, incomplete evidence and unresolved transactions fail closed. No migrations, credential changes, new enablement or notification replay are performed.

Stable v1.0.0 is refused: equal migration schemas do not establish semantic safety. Its positive permanent ZFS data errors can falsely recover incidents. A guarded or non-running downgrade does not satisfy the resumed rollback release gate.

## Entry point

On a separately authorized disposable Linux installation, run the reviewed bundle's `scripts/lifecycle.py` with trusted `/usr/bin/python3 -I -B -S`. Actions are `plan`, `upgrade`, `rollback`, and `recover`; all require `--previous-wheel` pointing at the pinned predecessor. Rollback/recover additionally require `--transaction` naming the retained transaction directory. `plan` only checks artifact/schema prerequisites; runtime guards and semantic execution still need validation. Do not interpret its output as permission to mutate a host.

Every executable transition validates both artifact identity and synthetic ZFS semantics. Candidate launchers and activation scripts target the final `/opt/rackmarshal/venv` path. The transaction retains old code, protected-file backups, SQLite backup plus restoration proof, and a durable journal under `/opt/rackmarshal/lifecycle-transactions`. Preparation receipts remain under `/opt/rackmarshal/lifecycle-inputs`. Retain both directories and exact artifacts for investigation.

The runtime adapter installs persistent maintenance conditions, quiesces timers before services and refuses active oneshots. Base unit payloads remain identical; this private path does not implement arbitrary unit changes. It verifies effective typed systemd conditions before activation. Rollback preserves the current database, newer observations, configuration and credentials; it never restores an older database. Changed protected files require investigation rather than automatic replacement.

`RESUME_AUTHORIZED` is the durable acceptance decision before removing the maintenance marker. `COMMITTED` or `ROLLED_BACK` is written only after restoring the recorded runtime state. A crash after authorization can boot the accepted code according to existing enablement, which may differ from the previous active-state snapshot. Explicit recover reconciles retained inventories and journal state and restores the pinned predecessor; it does not silently restart an unknown version. A failed/incomplete transition is not a pass. Retry of a completed rollback is refused; use a new upgrade transaction for re-upgrade.

## Remaining qualification

Local synthetic tests do not prove real systemd behavior. Independent review, exact-artifact disposable Linux upgrade/rollback/re-upgrade with newer data, interruption/reboot checks, fresh-install checks, client gates and the observation window remain required before release. See `docs/development/STATE_PRESERVING_LIFECYCLE_DESIGN.md`. No deployment or publication is authorized by this document.
