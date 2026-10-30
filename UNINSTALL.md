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

The 1.3 fresh installer refuses to run when any RackMarshal installation path, service account or unit is still present, including after a standard uninstall that preserved state. Do not run it as an upgrade or delete preserved state to get past that check. To start over, use `--purge` (after backing up anything you want to keep) or a fresh container or VM. See [UPGRADE.md](UPGRADE.md).
