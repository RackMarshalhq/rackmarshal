# RackMarshal Configuration

RackMarshal uses a simple `KEY=value` configuration file. The default location is:

```text
/etc/rackmarshal/rackmarshal.conf
```

The path can be overridden for compatible commands/processes with `RACKMARSHAL_CONFIG`. The migration command also accepts `RACKMARSHAL_STATE_DB` (or `STATE_DB`) as a database-path override.

## Base configuration

The installer creates these base values when no configuration already exists:

```text
SITE_NAME=rackmarshal
STATE_DB=/var/lib/rackmarshal/state.db
INSTALL_ROOT=/opt/rackmarshal
VENV_PYTHON=/opt/rackmarshal/venv/bin/python
STATUS_API_LISTEN_ADDRESS=127.0.0.1
STATUS_API_LISTEN_PORT=9110
```

`STATE_DB` is required by the shared configuration layer. The status API address and port control the local status service. Keep the status API bound to loopback unless you deliberately provide appropriate network access controls.

## Enabling monitoring domains

A base install is intentionally safe and schedules no infrastructure collectors. To turn one on after installation, edit `/etc/rackmarshal/rackmarshal.conf`: add that domain's required site values and list the domain in `ENABLED_DOMAINS` (a comma-separated subset of `pve,zfs,backup,ha,hardware,mount`). Then check the file and start the domain's timer yourself:

```bash
sudo /opt/rackmarshal/venv/bin/rackmarshal validate-config --config /etc/rackmarshal/rackmarshal.conf
sudo systemctl enable --now rackmarshal-domain@zfs.timer     # use the domain you are enabling
```

The installer cannot be run again for this: it refuses to run over an existing installation. **For `pve`, `zfs`, `backup` and `ha`, record a baseline first** (next section; there is no backup tool yet), or every resource they find is reported as new and opens an incident.

Run `rackmarshal validate-config --config /etc/rackmarshal/rackmarshal.conf` before enabling a domain. Use `rackmarshal domains` to list supported domain identifiers and `rackmarshal diagnostic` for a non-secret operational summary.

## Baselines: telling RackMarshal what healthy looks like

RackMarshal compares what it sees with a **baseline**, a stored record of what you decided is normal. A resource with no baseline is reported as `NEW` and opens an incident. The baselines live in the database, so every installation starts with none.

Operator tools in the installer bundle record them. Both are insert-only: they never change an existing baseline. Each prints a plan and writes nothing until you add `--apply`, and `--apply` needs root and first writes a backup of the database.

1. Record one observation **without** running the full cycle, so nothing is compared or alerted yet. For ZFS, as the service account:

   ```bash
   sudo -u rackmarshal env RACKMARSHAL_CONFIG=/etc/rackmarshal/rackmarshal.conf RACKMARSHAL_STATE_DB=/var/lib/rackmarshal/state.db \
     sh -c '/opt/rackmarshal/venv/bin/python -m rackmarshal.domains.zfs.collector | /opt/rackmarshal/venv/bin/python -m rackmarshal.domains.zfs.observation'
   ```

   It prints an `observation_id`. The observation must be less than 15 minutes old when you adopt it.

2. Look at what that observation contains, then adopt the pools you have checked are healthy. From the extracted bundle:

   ```bash
   sudo mkdir -m 700 /root/rackmarshal-baseline-backups
   sudo /opt/rackmarshal/venv/bin/python -I -B scripts/adopt-zfs-baseline.py --db /var/lib/rackmarshal/state.db \
     --observation-id 1 --pool tank --approval-note "I checked zpool status -v on 2026-11-01" \
     --backup-dir /root/rackmarshal-baseline-backups          # prints the plan only
   # add --apply once the plan is what you expect
   ```

The ZFS tool refuses a pool that is not `ONLINE`, that does not report a permanent error count of exactly zero, or whose devices are not `ONLINE`. Check `zpool status -v` yourself first: the baseline says "this is normal", and a pool that already has damage should be fixed, not recorded as normal. Home Assistant works the same way with `scripts/adopt-ha-baseline.py`: record one observation with `rackmarshal.domains.ha.collector | rackmarshal.domains.ha.observation` (run it as the service account, like the ZFS command above), then adopt with `--observation-id N --resource home_assistant_api --resource home_assistant_core`. It adopts a resource only when it reports the status the collector expects (`OK` or `RUNNING`). Without a Home Assistant baseline the Home Assistant cycle stops with the error "Home Assistant baseline is empty". PVE guests use `scripts/adopt-pve-baseline.py` (see [PVE baseline adoption](docs/architecture/PVE_BASELINE_ADOPTION.md)). **There is no tool for backup baselines yet in this release candidate**, because a backup baseline needs policy choices (schedules, retention, how old a snapshot may be) that an observation cannot supply; do not enable the `backup` domain until there is one.

## Optional path overrides

The shared configuration layer also supports:

- `CONFIG_DIR`
- `STATE_DIR`
- `DOMAINS_DIR`
- `HA_CREDENTIAL_FILE`
- `PVE_API_ENV`
- `PBS_API_ENV`
- `PVE_CA_FILE`
- `PBS_CA_FILE`

Default credential/certificate paths are under `/etc/rackmarshal`; these files are intentionally **not** created with real credentials by the release bundle.

## Integration credential files

The PVE collector expects the PVE environment file to contain:

```text
PVE_API_URL=...
PVE_TOKEN_ID=...
PVE_TOKEN_SECRET=...
```

PVE-backed backup and mount collection also require `PVE_NODE` in `rackmarshal.conf`.

The backup collector additionally expects the PBS environment file to contain:

```text
PBS_API_URL=...
PBS_TOKEN_ID=...
PBS_TOKEN_SECRET=...
PBS_DATASTORE=...
```

The Home Assistant collector expects its credential file to provide `HA_URL` and `HA_TOKEN`.

The Home Assistant collector and notification delivery worker source this file
with Bash; it is trusted executable shell configuration, not an inert dotenv
parser. Keep it administrator-owned and writable only by its administrator,
readable by the service account as needed. Do not use downloaded or
less-trusted input as this file. The generic RackMarshal configuration and
PVE/PBS key-value readers do not thereby gain shell evaluation.

Do not commit these credential files. Protect them with restrictive ownership and permissions appropriate to the RackMarshal service account.

## SSH-backed domains

ZFS uses these required site values:

- `ZFS_SSH_HOST`
- `ZFS_SSH_USER`
- `ZFS_SSH_KEY`
- `ZFS_KNOWN_HOSTS`

Hardware and mount collection also support SSH configuration with corresponding `HARDWARE_*` and `MOUNT_*` host/user/key/known-hosts settings. Host keys should be explicitly trusted; do not disable strict host-key checking merely to simplify setup.

## Hardware thresholds

The current hardware incident logic requires site-defined values for:

- `HARDWARE_HOT_THRESHOLD_C`
- `HARDWARE_HOT_REQUIRED_SAMPLES`
- `HARDWARE_URGENT_THRESHOLD_C`
- `HARDWARE_RECOVERY_THRESHOLD_C`
- `HARDWARE_RECOVERY_REQUIRED_SAMPLES`

Hardware inventory requires `HARDWARE_NVME_SERIALS`; for each serial, define `HARDWARE_NVME_<SERIAL>_MODEL` and `HARDWARE_NVME_<SERIAL>_ROLE`. It also requires `HARDWARE_SSH_HOST`, `HARDWARE_SSH_USER`, `HARDWARE_SSH_KEY`, and `HARDWARE_KNOWN_HOSTS`.

## Backup and mount policy settings

Current backup comparison logic recognizes `BACKUP_TM_SLA_HOURS`, `BACKUP_TM_ALERT_TARGETS`, and `BACKUP_EXCLUDE_VMIDS`. The optional PBS store probe uses `BACKUP_SSH_HOST`, `BACKUP_SSH_USER`, `BACKUP_SSH_KEY`, and `BACKUP_KNOWN_HOSTS`.

Mount collection can use `MOUNT_CATALOG_FILE`, `MOUNT_SSH_HOST`, `MOUNT_SSH_USER`, `MOUNT_SSH_KEY`, `MOUNT_KNOWN_HOSTS`, and `MOUNT_DELIVER_TIMEOUT_S`. A generic catalog placeholder is provided at `config/mounts.catalog.example.toml`; it intentionally contains no real topology.

## Local AI and evidence options

The shared configuration layer currently recognizes `LOCAL_AI_ENABLED`, `LOCAL_AI_TIMEOUT_SECONDS`, and `LOCAL_AI_ATTACH_TO_NOTIFY`. Evidence export recognizes the `RACKMARSHAL_STATUS_URL`, `RACKMARSHAL_EVIDENCE_RETAIN_DAYS`, and `RACKMARSHAL_EVIDENCE_RETENTION_CLASS` environment variables.

These capabilities are development-stage components. Do not assume a default base installation has configured an AI service or an evidence-retention policy.

## Configuration ownership

The installer preserves an existing `/etc/rackmarshal/rackmarshal.conf` on subsequent installs. Upgrade procedures therefore do not silently replace site configuration. Review release notes for new keys before enabling new domains.

Operator-selected Python, comparator and explainer paths are code-execution
choices. Likewise, tools invoked by name (`bash`, `systemctl`, and Git in
operator scripts) resolve through the launch environment's PATH. Use a trusted
PATH containing only administrator-controlled directories; do not prepend a
working directory or a directory writable by a less-trusted account. This
applies especially when running installation or promotion commands as root.
Arguments are passed separately rather than interpolated into shell source,
but that does not make an untrusted executable or shell configuration safe.

The packaged services use the unprivileged RackMarshal account, absolute Python
entrypoints, `NoNewPrivileges` and filesystem protections. These constrain
service execution; they do not validate administrator overrides, grant safe
execution of untrusted configuration, or protect against malicious operator
code. The installer creates new configuration as root-owned and preserves
existing configuration. It does not silently repair pre-existing ownership or
permission mistakes.


## Read-only setup guidance (1.2 development)

Run `rackmarshal setup-plan --config /etc/rackmarshal/rackmarshal.conf` to see supported domain selection, missing required key names, and credential/certificate/catalog file readiness. Output omits configuration values, paths and credential contents. It writes nothing and performs no network or service actions. Exit 2 indicates invalid/incomplete configuration; exit 0 means these configuration checks pass, including a valid base install with all domains disabled. It is not a resource-health check.

A complete configuration still requires explicit collector setup and recorded observations. The dashboard distinguishes enabled selection, disabled historical records and unavailable selection; none of those labels proves current resource health. Domain support does not imply every resource is monitored. Downloads, general network monitoring and storage capacity are not covered.
