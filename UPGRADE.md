# Upgrading RackMarshal

The current installer is designed to be safely rerun against an existing RackMarshal installation.

## Before upgrading

Back up at least:

```text
/etc/rackmarshal/
/var/lib/rackmarshal/state.db
```

If you keep additional site-specific keys, certificates, catalogs, or credential files elsewhere, back those up according to your own configuration.

## Upgrade procedure

Extract the new RackMarshal release bundle and run its installer using the wheel from that same release:

```bash
sudo ./scripts/install.sh \
  --wheel ./rackmarshal-VERSION-py3-none-any.whl
```

The installer force-reinstalls the Python package into the existing RackMarshal virtual environment, preserves an existing `rackmarshal.conf`, applies pending database migrations, refreshes the supplied systemd units, and starts/verifies the base services.

## Database migrations

RackMarshal records applied schema migrations. Already-applied migrations are not reapplied during a normal upgrade.

Do not manually edit the migration ledger or alter an existing migration file in a deployed release.

## After upgrading

Verify the status service and notification timer, then check the health endpoint. Review the changelog and configuration documentation for any newly introduced site settings before enabling affected collectors.

## Upgrade validation

Before an upgrade, run `rackmarshal validate-config`. The installer preserves site configuration, applies only pending migrations, and refreshes systemd units. After upgrading, run `rackmarshal diagnostic` and verify `/health`. If an upgrade fails before completion, retain the pre-upgrade configuration/database backup and do not manually edit the migration ledger.

## Release-candidate rollback

Test upgrades on a disposable host first. Quiesce the status service and all enabled domain/notification timers and wait for in-flight jobs before taking a consistent SQLite backup. Retain the exact previous installer/wheel, configuration, database backup, and systemd units/drop-ins. Record hashes and permissions.

For an unsuccessful upgrade with no accepted intervening writes, keep workloads stopped, reinstall the previous wheel, restore the saved configuration and units (remove candidate-only drop-ins), run daemon-reload, and verify the prior version and health before restoring the prior timer/service state. Restore the pre-upgrade database only when needed for schema rollback, and only while all writers are stopped; this deliberately loses post-backup records. For a successful upgrade with later observations, prefer compatible code rollback that preserves history. Never erase production history merely to undo an incident or baseline decision.

The 1.1.0rc1 candidate retains the 1.0.0 migration set. Exact artifact install/upgrade/rollback qualification is recorded separately from this procedure. The base installer is not an automatic transactional rollback manager.
