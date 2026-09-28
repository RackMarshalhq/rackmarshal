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

This behavior is intentional so configuration and operational state survive an uninstall/reinstall cycle.

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

Run the normal installer again. The preserved configuration and database are reused and pending migrations are applied.
