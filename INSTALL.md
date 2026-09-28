# Installing RackMarshal

## Current support boundary

The reference installer has been exercised on a fresh Debian 12 system. It is written for Debian/Ubuntu-compatible Linux systems using systemd and requires root privileges.

RackMarshal requires Python 3.11 or newer. On systems with `apt-get`, the installer can bootstrap `python3` and `python3-venv` when needed.

The current development package is not a stable production release.

## Release bundle

The installer release bundle contains:

- the RackMarshal Python wheel
- `scripts/install.sh`
- `scripts/uninstall.sh`
- systemd service/timer definitions
- the Apache-2.0 license

Extract the release bundle on the target host and change into its top-level directory.

## Install

Run the installer as root and point it at the wheel shipped in the same release bundle:

```bash
sudo ./scripts/install.sh \
  --wheel ./rackmarshal-1.0.0-py3-none-any.whl
```

A custom initial configuration file may be supplied with `--config`. Existing RackMarshal configuration is never replaced by that option.

To install without starting RackMarshal immediately:

```bash
sudo ./scripts/install.sh \
  --wheel ./rackmarshal-1.0.0-py3-none-any.whl \
  --no-start
```

## What the installer creates

- system user/group: `rackmarshal`
- application environment: `/opt/rackmarshal/venv`
- configuration directory: `/etc/rackmarshal`
- state directory: `/var/lib/rackmarshal`
- log directory: `/var/log/rackmarshal`
- SQLite state database: `/var/lib/rackmarshal/state.db`
- `rackmarshal-status.service`
- `rackmarshal-notify.service`
- `rackmarshal-notify.timer`

The configuration directory is root-owned and group-readable by RackMarshal. State and log directories are owned by the RackMarshal service account.

## Verification

With the default configuration, the status API listens only on `127.0.0.1:9110`.

```bash
systemctl status rackmarshal-status.service
systemctl status rackmarshal-notify.timer
curl http://127.0.0.1:9110/health
```

The health endpoint should return an HTTP 200 response. See [CONFIGURATION.md](CONFIGURATION.md) before enabling infrastructure collectors.
