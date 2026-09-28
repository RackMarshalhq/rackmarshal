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

## Migration from HomelabOps

The installer bundle includes `migrate-from-homelabops.sh` and `rollback-to-homelabops.sh`. The migration tool records the previously enabled/active HomelabOps units, copies configuration and state into RackMarshal-owned locations, applies only pending RackMarshal migrations, validates the resulting configuration, and starts only the corresponding RackMarshal domains. The legacy installation is left in place so rollback remains possible.

Before migrating a production instance, prove both migration and rollback against a disposable restored copy of that instance. Do not use the production instance as the first migration target.
