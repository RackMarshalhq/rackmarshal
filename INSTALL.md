# Installing RackMarshal

## What this installs, and what it needs

RackMarshal 1.3 installs on a **fresh** Debian or Ubuntu machine (a small LXC container or VM is fine) that uses systemd and has Python 3.11 or newer with the `venv` module. Debian 12 is the reference platform.

- **Fresh installs only.** The installer refuses to run if any RackMarshal directory, service account or systemd unit already exists. It never upgrades, repairs or reinstalls over an existing installation. See [UPGRADE.md](UPGRADE.md) for moving from an earlier release.
- **Nothing is downloaded.** The installer does not run `apt`, `pip` or any network operation. Install Python 3.11+, `python3-venv` and the standard systemd tools yourself first (on Debian or Ubuntu: `sudo apt install python3 python3-venv`).
- **Root is required**, and the installer must be run from the extracted bundle.
- **Release candidate.** 1.3.0 release candidates have not completed the release gate. The exact-artifact qualification result for each release is stated in its release notes. Use a disposable container or VM, or take a snapshot, until you are comfortable.

## Get and verify the files

Download these from the release page into one folder:

- `rackmarshal-installer-<version>.tar.gz` (the installer bundle)
- `SHA256SUMS`

Check the download before you run anything from it:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

Every file you downloaded should report `OK`. Get `SHA256SUMS` from the release page itself. The checks inside the bundle detect accidental changes but cannot prove the archive was not replaced by someone else.

## Install

```bash
tar -xzf rackmarshal-installer-<version>.tar.gz
cd rackmarshal-installer-<version>
sudo ./scripts/install.sh --wheel ./rackmarshal-<version>-py3-none-any.whl
```

Use the version in your file names, for example `rackmarshal-installer-1.3.0-rc1` and `rackmarshal-1.3.0rc1-py3-none-any.whl`.

Optional flags:

- `--config /path/to/rackmarshal.conf` supplies the initial configuration. An existing configuration is never replaced.
- `--no-start` installs without starting the services.

On success the installer ends with `RACKMARSHAL_INSTALL_OK`. It also prints a staging folder under `/run` that holds receipts of what it checked. `/run` is cleared on reboot, so copy that folder somewhere durable if you want to keep the record.

**If the installer fails:** it stops and keeps what it had done so you can inspect it. It does not retry, delete or roll back by itself. Do not delete directories by hand to get past the "existing installation" check. Copy the output and open an issue, then retry in a fresh container or VM.

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
- one `rackmarshal-domain@<name>` timer for each domain listed in `ENABLED_DOMAINS`

The configuration directory is root-owned and group-readable by RackMarshal. State and log directories are owned by the RackMarshal service account. A base install enables no monitoring domains.

## Verification

With the default configuration, the status API listens only on `127.0.0.1:9110`.

```bash
systemctl status rackmarshal-status.service
systemctl status rackmarshal-notify.timer
curl http://127.0.0.1:9110/health
```

The health endpoint should return HTTP 200. See [CONFIGURATION.md](CONFIGURATION.md) before enabling infrastructure collectors.

## Read-only setup guidance

Run `rackmarshal setup-plan --config /etc/rackmarshal/rackmarshal.conf` to see supported domain selection, missing required key names, and credential/certificate/catalog file readiness. Output omits configuration values, paths and credential contents. It writes nothing and performs no network or service actions. Exit 2 indicates invalid or incomplete configuration; exit 0 means these configuration checks pass, including a valid base install with all domains disabled. It is not a resource-health check.

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
