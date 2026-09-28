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

A base install is intentionally safe and schedules no infrastructure collectors. Set `ENABLED_DOMAINS` to a comma-separated subset of `pve,zfs,backup,ha,hardware,mount`, provide that domain's required site configuration, then rerun the installer. The installer validates configuration before database changes and enables a dedicated systemd timer for each selected domain.

Run `rackmarshal validate-config --config /etc/rackmarshal/rackmarshal.conf` before enabling a domain. Use `rackmarshal domains` to list supported domain identifiers and `rackmarshal diagnostic` for a non-secret operational summary.

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

The Local-AI explanation subsystem is disabled by default. Set `LOCAL_AI_ENABLED=true`, `OLLAMA_URL`, and `OLLAMA_MODEL` to enable the asynchronous explainer. `LOCAL_AI_TIMEOUT_SECONDS` controls worker timeout and `LOCAL_AI_ATTACH_TO_NOTIFY` allows a completed advisory explanation to be attached to an OPENED notification. The AI explanation is advisory only and never changes incident state.

When enabled, the installer activates `rackmarshal-local-ai-explain.timer`; when disabled, that timer remains off. Evidence export also recognizes `RACKMARSHAL_STATUS_URL`, `RACKMARSHAL_EVIDENCE_RETAIN_DAYS`, and `RACKMARSHAL_EVIDENCE_RETENTION_CLASS`.

## Configuration ownership

The installer preserves an existing `/etc/rackmarshal/rackmarshal.conf` on subsequent installs. Upgrade procedures therefore do not silently replace site configuration. Review release notes for new keys before enabling new domains.

### Ignoring unmanaged PVE resources

`PVE_IGNORE_RESOURCES` is an optional comma-separated list of exact PVE identities in `type:key` form, for example `lxc:9001,lxc:9002`. Ignored resources are omitted from PVE observations and therefore do not open NEW incidents. If an ignored resource already has an OPEN NEW incident, the next PVE incident-processing cycle recovers it naturally because it is no longer present in the abnormal comparison set. Use this only for intentionally unmanaged/disposable resources; do not use it to hide production guests.

### Home Assistant recovery clearing

RackMarshal uses Home Assistant persistent notifications for incident OPENED events. When that incident later reaches RECOVERED, RackMarshal dismisses the exact previously-sent OPENED notification and records the RECOVERED delivery as sent in its own ledger. It does not create a second persistent RECOVERED notification. This keeps the HA notification surface aligned with currently open incidents while preserving recovery history in RackMarshal.
