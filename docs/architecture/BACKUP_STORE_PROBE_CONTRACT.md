# Backup store probe: JSON contract (private extension)

Status: **unsupported extension.** RackMarshal does not ship the program that produces this JSON. This page documents what the backup collector stores and what the comparator reads, so an operator can write their own. It is derived from the code in `rackmarshal/domains/backup/` and `rackmarshal/api/status.py`, not from any particular site.

## How it is wired

Set `BACKUP_SSH_HOST`, `BACKUP_SSH_USER` and `BACKUP_SSH_KEY` in `rackmarshal.conf` (and optionally `BACKUP_KNOWN_HOSTS`, default `/etc/rackmarshal/ssh/known_hosts`). The collector runs `ssh -i KEY -o BatchMode=yes -o StrictHostKeyChecking=yes USER@HOST ignored` with a 30 second limit, expects one JSON object on standard output, and stores it as `pbs_store_probe` in the backup observation. If any of the three settings is missing, nothing here runs. On failure the collector stores `{"_error": "..."}` and the probe-based checks report nothing.

The intended server-side design is an SSH key restricted with `restrict`, a `from=` address and a forced `command=` that runs a **read-only** program, so the key can do nothing else. The command text sent by the client is ignored.

## Top-level object

| Key | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `observed_at` | UTC time, ISO 8601 with `Z` |
| `primary`, `secondary` | Object keyed `"vm/100"` or `"ct/101"`. Each value: `kind`, `vmid`, `age_hours` (age of the newest file under that guest's folder; null if unknown), `newest_epoch`. Used for the status page counts and age. |
| `missing_on_secondary` | List of guest keys present in `primary` but not in `secondary`; null if either section failed |
| `section_errors` | Object `{section: {"state": "UNKNOWN", "reason": "<code>"}}` for sections that could not be measured. Failed sections are treated as unavailable, never as healthy. |
| `timemachine` | Object keyed by person: `exists` (bool), `age_hours`, `used` |
| `phones` | Object keyed by person: `exists` (bool), `age_hours` |
| `messages` | Object keyed by person: either `error`, or three objects `pull`, `snap`, `repl`, each with `age_hours` |
| `host_verify` | See below |
| `pbs_native_verify` | `status` (`"OK"` expected), `errors` (list), `age_hours` |
| `rsync_filebackups` | `status` (`"OK"` expected), `log_error` (bool), `finished`, `dest_exists`, `pool_mounted` (all true expected), `latest_log_age_s` |

`host_verify` fields: `result` (`success` or null), `exec_main_status` (0 or null), `status` (`ok` or null), `failed_count` (0 or null), `failing_checks` (list of names), `age_hours`, `errors`.

## Which setting turns on which check

| Check | Needs |
| --- | --- |
| Time Machine | `BACKUP_TM_ALERT_TARGETS` (people), `BACKUP_TM_SLA_HOURS` |
| Phones | `BACKUP_PHONE_ALERT_TARGETS`, `BACKUP_PHONE_SLA_HOURS` (default 168) |
| Messages | `BACKUP_MESSAGES_ALERT_TARGETS`, `BACKUP_MESSAGES_SLA_HOURS` (default 36) |
| Host verification | the probe (always, once SSH is set); `BACKUP_HOST_VERIFY_SLA_HOURS` (24). Reports `homelab-backup-verification`; a probe without `host_verify` is reported as a problem. |
| PBS native verification | the probe (always, once SSH is set); `BACKUP_PBS_NATIVE_VERIFY_SLA_HOURS` (192). A probe without `pbs_native_verify` is reported as a problem. |
| rsync file-backups | `BACKUP_RSYNC_FILEBACKUPS_CHECK=true`; `BACKUP_RSYNC_FILEBACKUPS_SLA_HOURS` (30). Reports `homelab-rsync-backups`. |

An alert target with no matching entry in the probe is reported as missing, not skipped.

## Writing your own

- Keep the program read-only and bounded: finite paths, a time limit per section, an output size limit, and a section error instead of a crash. A section you cannot measure must be reported in `section_errors`, never left out or filled with a healthy-looking value.
- Print exactly one JSON line. Never print secrets.
- Do not put personal names, device identifiers or private paths in anything you publish.
- Test it with `ssh` as the forced-command key, from the address in `from=`, before enabling the settings.
