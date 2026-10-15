# Installing RackMarshal

## Current support boundary

The reference installer has been exercised on a fresh Debian 12 system. It is written for Debian/Ubuntu-compatible Linux systems using systemd and requires root privileges.

RackMarshal requires Python 3.11 or newer. On systems with `apt-get`, the installer can bootstrap `python3` and `python3-venv` when needed.

RackMarshal 1.0.0 is the first stable public release. The reference installation path was qualified on a disposable Debian 12 host; other Debian/Ubuntu-compatible environments should be treated as additional validation targets.

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


## Read-only setup guidance (1.2 development)

Run `rackmarshal setup-plan --config /etc/rackmarshal/rackmarshal.conf` to see supported domain selection, missing required key names, and credential/certificate/catalog file readiness. Output omits configuration values, paths and credential contents. It writes nothing and performs no network or service actions. Exit 2 indicates invalid/incomplete configuration; exit 0 means these configuration checks pass, including a valid base install with all domains disabled. It is not a resource-health check.

A complete configuration still requires explicit collector setup and recorded observations. The dashboard distinguishes enabled selection, disabled historical records and unavailable selection; none of those labels proves current resource health. Domain support does not imply every resource is monitored. Downloads, general network monitoring and storage capacity are not covered.


## Optional Investigator

See [Investigator installation and verification](docs/architecture/INVESTIGATOR_INSTALLATION.md) for exact-wheel MCP setup, local marketplace installation, private hosted packaging and client qualification limits.

### Service access to the virtual environment

Installation sets umask `0027` explicitly and normalizes the complete virtual
environment to root ownership with the `rackmarshal` group: directories and
owner-executable files use `0750`; other regular files use `0640`. The group
cannot write code, and other users receive no access. Existing entries are
normalized as well as newly installed entries. Symlinks and their targets are
not changed. Foreign-owned entries, hard links, special files, or traversal
errors stop the permission pass before it starts applying changes.

Before configuration or migration work, a bounded interpreter/import probe runs
with the same user and group as the service. This catches owner-only virtualenv
paths even when a root installation command succeeds. A failed normalization
or probe is an installation failure and requires inspection, not automatic
service startup. Changed installer artifacts require fresh lifecycle validation.

## Private bootstrap candidate 1.2.0rc6.dev3

This candidate supports fresh installations only. Any existing install, configuration, state/log path, service account/group, or RackMarshal unit causes refusal before persistent changes. Upgrade, reinstall and rollback paths are not qualified. Preserve partial installations after failure; do not retry by deleting them.

Provision Python 3.11 or later with the standard-library venv module and systemd/account utilities separately. The installer never runs APT, ensurepip or host pip. It verifies all bundle hashes and ownership, stages copies privately under /run, creates a pip-less venv, and temporarily executes the unmodified pinned PyPA installer 1.1.0 wheel. Only the exact RackMarshal wheel is installed, with complete RECORD validation and no bytecode compilation. Neither pip nor installer is left in the runtime. Network operations are denied during bootstrap.

Obtain the installer archive digest from an independently trusted channel before executing it. The internal manifest detects alteration but cannot authenticate an attacker-replaced archive.

Use --no-start for qualification. Copy the reported staging directory and receipts to durable private evidence before reboot; /run is ephemeral. The cloud executor with UID65534-owned root ancestors is unsupported by the ownership verifier. Do not weaken checks or substitute ownership results. Mac tests and cloud non-root tests do not replace genuine Debian12 root/Python3.11 service-identity and lifecycle qualification.

The fresh-only rule remains in force. A separate restricted private dev2/dev3 lifecycle command is documented in UPGRADE.md; it does not broaden fresh-install behavior or establish release qualification.
