# Uninstalling RackMarshal

RackMarshal provides two uninstall modes.

## Standard uninstall

```bash
sudo ./scripts/uninstall.sh
```

The standard uninstall:

- disables/stops the RackMarshal status service and notification timer
- removes the installed RackMarshal systemd unit files
- removes `/opt/rackmarshal`
- **preserves** `/etc/rackmarshal`
- **preserves** `/var/lib/rackmarshal`
- leaves the service account available

Configuration and operational state survive standard removal. Retain lifecycle transaction and preparation receipts separately before any separately authorized uninstall; they are under `/opt/rackmarshal`.

## Purge

```bash
sudo ./scripts/uninstall.sh --purge
```

Purge additionally removes:

- `/etc/rackmarshal`
- `/var/lib/rackmarshal`
- `/var/log/rackmarshal`
- the `rackmarshal` system user/group when removal succeeds

`--purge` is destructive. Back up any state, configuration, credentials, certificates, or other site files you intend to keep before using it.

## Reinstallation after standard uninstall

The private dev2/dev3 fresh installer refuses preserved installation paths. Do not run it as an upgrade or delete preserved state to bypass this guard. Reusing a partially removed installation requires an explicitly reviewed recovery procedure; the lifecycle CLI requires its recognized complete installation and retained transaction state. See UPGRADE.md.
