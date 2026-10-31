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

The installer cannot be run again for this: it refuses to run over an existing installation. **For `pve`, `zfs`, `backup` and `ha`, record a baseline first** (next section; the backup tool exists but the domain is still unsupported for new installs, see below), or every resource they find is reported as new and opens an incident.

Run `rackmarshal validate-config --config /etc/rackmarshal/rackmarshal.conf` before enabling a domain. Use `sudo /opt/rackmarshal/venv/bin/rackmarshal domains` to list supported domain identifiers and `sudo /opt/rackmarshal/venv/bin/rackmarshal diagnostic` for a non-secret operational summary (the application folder is readable only by root and the `rackmarshal` group).

## Baselines: telling RackMarshal what healthy looks like

RackMarshal compares what it sees with a **baseline**, a stored record of what you decided is normal. A resource with no baseline is reported as `NEW` and opens an incident. The baselines live in the database, so every installation starts with none.

Operator tools in the installer bundle record them. Both are insert-only: they never change an existing baseline. Each prints a plan and writes nothing until you add `--apply`, and `--apply` needs root and first writes a backup of the database.

1. Record one observation **without** running the full cycle, so nothing is compared or alerted yet. For ZFS, as the service account:

   ```bash
   sudo -u rackmarshal env RACKMARSHAL_CONFIG=/etc/rackmarshal/rackmarshal.conf RACKMARSHAL_STATE_DB=/var/lib/rackmarshal/state.db \
     sh -c '/opt/rackmarshal/venv/bin/python -m rackmarshal.domains.zfs.collector | /opt/rackmarshal/venv/bin/python -m rackmarshal.domains.zfs.observation'
   ```

   It prints an `observation_id`. The observation must be less than 15 minutes old when you adopt it.

2. Look at what that observation contains, then adopt the pools you have checked are healthy. As root, from the extracted bundle folder (`/root/rm-install/rackmarshal-installer-<version>`, see [INSTALL.md](INSTALL.md)):

   ```bash
   sudo mkdir -m 700 /root/baseline-backups
   sudo /opt/rackmarshal/venv/bin/python -I -B scripts/adopt-zfs-baseline.py --db /var/lib/rackmarshal/state.db \
     --observation-id 1 --pool tank --approval-note "I checked zpool status -v on 2026-11-01" \
     --backup-dir /root/baseline-backups          # prints the plan only
   # add --apply once the plan is what you expect
   ```

**Backup baseline (new, domain still unsupported).** `scripts/adopt-backup-baseline.py` records one backup job and the guests you name. Record a `backup_domain` observation first (`python -m rackmarshal.domains.backup.collector | python -m rackmarshal.domains.backup.observation`; it must be less than 2 hours old), look at it, then run the tool with `--job <job id>`, one `--guest <id>` per guest, `--max-age-hours <n>` (how old the newest backup of each guest may get before RackMarshal alerts; your choice), `--approval-note` and `--backup-dir`. It prints a plan and writes nothing until you add `--apply`. It refuses a disabled job, a guest that is not covered by the job, has no backup, or whose newest backup is not verified `ok` or is already older than your limit, and anything that would overwrite an existing baseline. RackMarshal supports exactly one backup job baseline.

The ZFS tool refuses a pool that is not `ONLINE`, that does not report a permanent error count of exactly zero, or whose devices are not `ONLINE`. Check `zpool status -v` yourself first: the baseline says "this is normal", and a pool that already has damage should be fixed, not recorded as normal. Home Assistant works the same way with `scripts/adopt-ha-baseline.py`: record one observation with `rackmarshal.domains.ha.collector | rackmarshal.domains.ha.observation` (run it as the service account, like the ZFS command above), then adopt with `--observation-id N --resource home_assistant_api --resource home_assistant_core`. It adopts a resource only when it reports the status the collector expects (`OK` or `RUNNING`). Without a Home Assistant baseline the Home Assistant cycle stops with the error "Home Assistant baseline is empty". PVE guests use `scripts/adopt-pve-baseline.py` (see [PVE baseline adoption](docs/architecture/PVE_BASELINE_ADOPTION.md)). **There is no tool for backup baselines yet in this release candidate**, because a backup baseline needs policy choices (schedules, retention, how old a snapshot may be) that an observation cannot supply; do not enable the `backup` domain until there is one.

## Database snapshots

The installer enables a daily timer, `rackmarshal-db-snapshot.timer` (03:15 UTC), that writes a consistent copy of the state database to `/var/lib/rackmarshal/db-snapshots/`. Each copy is checked with SQLite's `quick_check` before it is kept, and a copy that fails is discarded. The newest copy is also kept as `state.db.latest`. The installer runs one snapshot at the end of a normal install and fails if it does not succeed.

- **Disk space.** Each snapshot is a full copy of the database. Plan for roughly (kept snapshots + 1) times the database size; with the default of 7 kept, that is 8 times. A snapshot is refused, with an error in the journal, when the disk has less than twice the database size free, so it cannot fill the disk. The weekly observation prune (see the prune section below) keeps the observation tables from growing without limit; events and incidents are kept.
- **Keep more or fewer.** Set `RACKMARSHAL_DB_SNAPSHOT_RETENTION` (and, if you want another folder, `RACKMARSHAL_DB_SNAPSHOT_DIR`) with `sudo systemctl edit rackmarshal-db-snapshot.service` and an `[Service]` section containing `Environment=` lines. If you move the folder, also add it to `ReadWritePaths=` there.
- **Restore.** Snapshots are ordinary SQLite files. Stop the services and timers, keep a copy of the current database, copy the snapshot over `state.db` with the same owner and mode (`rackmarshal:rackmarshal`, `0640`), run `PRAGMA integrity_check` on it, then start them again. Practise this once on a spare machine before you need it.
- **Not a backup of the machine.** The copies live on the same disk as the database. Copy them off the machine if you want protection against disk loss.

## Investigator MCP service (optional)

The read-only MCP server that the Investigator uses can run as a service. It listens on loopback only, so nothing outside the machine can reach it. The installer does not start it. Install it into the same environment, then:

```bash
sudo /opt/rackmarshal/venv/bin/pip install 'rackmarshal[mcp]'   # or the wheel you installed, with [mcp]
sudo install -m 0644 packaging/systemd/optional/rackmarshal-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rackmarshal-mcp.service
/opt/rackmarshal/venv/bin/rackmarshal investigator-check          # expect exit 0
```

Reaching it from a hosted assistant needs a secure connection that you set up and own (for example your provider's tunnel program with your own profile and credentials). RackMarshal does not ship one, and no credential belongs in the repository or in `rackmarshal.conf`. See `docs/architecture/INVESTIGATOR_INSTALLATION.md`.

## Self-watch (optional)

Self-watch is RackMarshal watching itself every five minutes. It opens an incident, with the usual notification, when the status service is down, when the timer of a domain you enabled is not running or its service has failed, when a domain you enabled has no data or stale data, or when notifications cannot be delivered. It only looks at the domains in `ENABLED_DOMAINS` and the real 1.3 units (`rackmarshal-status.service`, `rackmarshal-domain@<name>.timer` and `.service`). It also adds a `self_watch` section to the status page. Turn it on with:

```bash
sudo install -m 0644 packaging/systemd/optional/rackmarshal-self-watch.service packaging/systemd/optional/rackmarshal-self-watch.timer /etc/systemd/system/
sudo install -d -m 0755 /etc/systemd/system/rackmarshal-self-watch.service.d
sudo install -m 0644 packaging/systemd/rackmarshal-self-watch.service.d/20-cycle-health.conf /etc/systemd/system/rackmarshal-self-watch.service.d/
sudo systemctl daemon-reload
sudo systemctl enable --now rackmarshal-self-watch.timer
sudo systemctl start rackmarshal-self-watch.service            # run once now
systemctl show rackmarshal-self-watch.service -p Result --value  # expect: success
```

The second and third commands attach result recording (the installer does that itself only if self-watch was already present when it ran). Alerts need a working notification path (see the Home Assistant settings above); without one, incidents are recorded but not delivered. A configuration with no `ENABLED_DOMAINS` line at all is treated as an older layout and watches every domain. The installer does not enable self-watch, and the uninstaller removes it.

## Daily evidence export (optional)

`rackmarshal.evidence.export` writes a dated folder of evidence (the status page contents, a schema and some database extras, with an `EVIDENCE.md` summary) under `/var/lib/rackmarshal/evidence/`, and deletes dated folders older than the retention you give. It reads the status page, so the status service must be running. To run it every day at 04:30 UTC:

```bash
sudo install -m 0644 packaging/systemd/optional/rackmarshal-evidence-export.service packaging/systemd/optional/rackmarshal-evidence-export.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rackmarshal-evidence-export.timer
sudo systemctl start rackmarshal-evidence-export.service       # run once now
sudo ls /var/lib/rackmarshal/evidence/                           # a dated folder appears
```

The unit keeps 35 days (`--retain-days 35`; edit the `ExecStart` line with `sudo systemctl edit --full rackmarshal-evidence-export.service` to change it). If you changed the status page address, set `RACKMARSHAL_STATUS_URL` in the same way. The installer does not enable it, and the uninstaller removes it. The evidence folder is not part of the database snapshots.

## Restricting who can read the status page (optional)

By default the status page listens on `127.0.0.1` only and needs nothing more. If you set `STATUS_API_LISTEN_ADDRESS` to a network address so that other machines (Home Assistant, a monitor) can read it, anyone who can reach that address can read your incident list. To limit it to named callers with the machine's own firewall (nftables; the Proxmox firewall is not involved):

1. Install nftables if it is missing (`sudo apt install nftables`; the RackMarshal installer itself is offline).
2. As root, from the extracted bundle folder, list the callers and write the rule file. Include this machine's own address if it reads its own page, and check the result before using it:

   ```bash
   sudo sh -c 'umask 022; python3 -I -B scripts/status-acl.py --allow 192.0.2.10 --allow 192.0.2.0/28 > /etc/rackmarshal/status-acl.nft'
   cat /etc/rackmarshal/status-acl.nft
   sudo nft -c -f /etc/rackmarshal/status-acl.nft    # syntax check; changes nothing
   ```

3. Install and start the rule: `sudo install -m 0644 packaging/systemd/optional/rackmarshal-status-acl.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now rackmarshal-status-acl.service`
4. Test from an allowed machine (the page answers) and from one that is not listed (the connection hangs and then times out). Keep another way into the machine open until you have tested.

The rule only affects the status port; loopback is always allowed and everything else is untouched. To remove it: `sudo systemctl disable --now rackmarshal-status-acl.service`. The uninstaller removes the unit. After you change the caller list, regenerate the file and run `sudo systemctl restart rackmarshal-status-acl.service`.

## Observation retention

The installer enables a weekly timer, `rackmarshal-observation-prune.timer` (Sundays 04:05 UTC), that deletes stored observations older than 35 days. Without it the database grows without limit. It always keeps the newest two observations of each kind, never deletes the observation a processor is still working from, and removes an observation together with its processing record in one transaction per batch. It does not delete baselines, incidents or events (the evidence behind incidents), so those rows still accumulate slowly; they are small compared with observations. It does not shrink the file: freed space is reused by new data.

- **Check what it would do.** `sudo -u rackmarshal env RACKMARSHAL_CONFIG=/etc/rackmarshal/rackmarshal.conf RACKMARSHAL_STATE_DB=/var/lib/rackmarshal/state.db /opt/rackmarshal/venv/bin/python -m rackmarshal.maintenance.prune --dry-run`
- **Keep more or fewer days.** Set `RACKMARSHAL_OBSERVATION_RETAIN_DAYS` (minimum 7) with `sudo systemctl edit rackmarshal-observation-prune.service` and an `[Service]` section containing an `Environment=` line.
- **Snapshots first.** Take a manual snapshot (see Database snapshots) before the first prune on a database that is already large.

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
PVE_API_URL=https://pve.example.invalid:8006/api2/json
PVE_TOKEN_ID=user@realm!tokenname
PVE_TOKEN_SECRET=...
```

`PVE_API_URL` must end in `/api2/json`; the collector adds its own paths to it, and without the ending Proxmox answers HTTP 500 "no such file". Give the token the read-only `PVEAuditor` role (for example `pveum acl modify / --tokens 'user@realm!tokenname' --roles PVEAuditor`); a token created with privilege separation has no permissions until you do. Certificate files named by `PVE_CA_FILE` must be owned by the service account with mode 0600.

**First run.** The Proxmox and backup incident processors work through observations strictly in order, so each needs a starting marker. You do not create it: the first time a processor runs on an empty ledger it writes the marker itself, at the newest earlier observation of the same kind if there is one (for example after carrying baselines from an older site), so the observation being processed is handled normally and a difference from the baseline opens an incident straight away. It logs `first run: ... starting marker created at observation N`. If the ledger is empty but incidents already exist, it refuses and tells you, because that suggests a restored or damaged database. After the first run a skipped observation is still reported as a gap. Do not start a domain service by hand right after enabling its timer: the timer runs it at once, and two runs in a row can create a gap.

PVE-backed backup and mount collection also require `PVE_NODE` in `rackmarshal.conf`.

The backup collector additionally expects the PBS environment file to contain:

```text
PBS_API_URL=...
PBS_TOKEN_ID=...
PBS_TOKEN_SECRET=...
PBS_DATASTORE=...
```

`PBS_API_URL` is the address of the backup server with the port and nothing after it, for example `https://pbs.example.invalid:8007`. Unlike `PVE_API_URL` it must **not** end in `/api2/json`, because the collector adds that itself. RackMarshal always verifies the server certificate, so the name in the URL must be one of the names the certificate is issued for (`PBS_CA_FILE` points at that certificate). A bare IP address fails with "certificate is not valid for" unless the certificate lists it. If the certificate lists a short name, use it and map it to the server's address in `/etc/hosts` on the RackMarshal machine (for example `192.0.2.10 pbs`). The token needs only a read-only role such as `DatastoreAudit` on the datastore.

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

**The `backup` domain is not supported for new installations in 1.3.** A backup baseline records choices only the operator can make (which jobs and guests, schedules, retention, how old a snapshot may be), and the tool that creates one (`scripts/adopt-backup-baseline.py`, below) is new and has not yet been proven on a fresh install. The comparator also contains checks written for one particular site. Do not add `backup` to `ENABLED_DOMAINS` on a new installation. A supported setup path is planned for a later release.

Current backup comparison logic recognizes `BACKUP_TM_SLA_HOURS`, `BACKUP_TM_ALERT_TARGETS`, and `BACKUP_EXCLUDE_VMIDS`. **SSH store probe: a private, unsupported extension.** The JSON it must print is documented in [docs/architecture/BACKUP_STORE_PROBE_CONTRACT.md](docs/architecture/BACKUP_STORE_PROBE_CONTRACT.md). When `BACKUP_SSH_HOST`, `BACKUP_SSH_USER` and `BACKUP_SSH_KEY` are all set (and optionally `BACKUP_KNOWN_HOSTS`), the collector runs a forced SSH command on the backup server and stores the JSON it prints. The program that produces that JSON is **not part of RackMarshal**, so the checks that read it cannot work unless you supply your own: phone and Messages backup age (`BACKUP_PHONE_*`, `BACKUP_MESSAGES_*`), Time Machine (`BACKUP_TM_*`), host verification (`BACKUP_HOST_VERIFY_SLA_HOURS`; reports `homelab-backup-verification`), PBS native verification (`BACKUP_PBS_NATIVE_VERIFY_SLA_HOURS`) and rsync file-backups. If you do not set the three SSH values, none of these run. If you do set them, host verification and PBS native verification report a problem whenever the probe JSON has no matching section. The rsync file-backups check (resource `homelab-rsync-backups`, limit `BACKUP_RSYNC_FILEBACKUPS_SLA_HOURS`, default 30) additionally runs only when you set `BACKUP_RSYNC_FILEBACKUPS_CHECK=true`.

Optional second Proxmox Backup Server datastore check (off by default). Set `BACKUP_SECONDARY_STORE` to the datastore name to turn it on. It uses the same PBS token and verified TLS as the primary collection, makes read-only calls, and reports two results: coverage (every enrolled guest has a copy, the copy is fresh, it is not behind the primary, and a verify task ran on that datastore) and capacity. A failure here never stops primary collection. Optional limits, with defaults: `BACKUP_SECONDARY_SNAPSHOT_SLA_HOURS` (36), `BACKUP_SECONDARY_SOURCE_LAG_GRACE_HOURS` (8), `BACKUP_SECONDARY_VERIFY_SLA_HOURS` (36), `BACKUP_SECONDARY_MIN_AVAILABLE_GIB` (64), `BACKUP_SECONDARY_MAX_UTILIZATION_PERCENT` (90). This does not change the "backup is not supported for new installations" rule above.

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
