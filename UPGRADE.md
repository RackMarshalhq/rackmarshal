# Upgrading RackMarshal

**RackMarshal 1.3 has no in-place upgrade.** The 1.3 installer installs fresh only and refuses to run when any RackMarshal directory, service account or systemd unit already exists. Do not delete preserved state to get around that check.

## Moving from 1.0.0 or 1.1.0 RC1

Install 1.3 on a new machine or container, set up the configuration and credentials again, and record baselines (see [CONFIGURATION.md](CONFIGURATION.md)). A new installation starts with a new history. Leave the old installation in place and running until you are satisfied with the new one; the 1.3 installer will not run on a machine that has RackMarshal on it.

## Checking a future upgrade (read-only)

`rackmarshal upgrade-plan --wheel rackmarshal-<version>-py3-none-any.whl --sums SHA256SUMS` shows whether a newer 1.3.x release could be applied safely. It also accepts `--sha256 <checksum>` for a checksum you copied from a different place than the download. It checks that the installed files still match the installed release (a hand patch is named), that the new file matches its checksum, that both versions are 1.3.x, and whether the database would need changing. If the new release adds database changes, it also rehearses them on a private copy of your database and checks that every table, column and row you had is kept. It changes nothing; applying is done by `rackmarshal upgrade`.

## `rackmarshal upgrade` (not yet supported)

`rackmarshal upgrade --bundle <extracted new installer> --wheel-sha256 <checksum> --previous-wheel <installed release wheel> --previous-sha256 <checksum>` runs the checks above against the wheel in the bundle and prints the exact command it would run. Only with `--apply --note "why"` (as root) does it run the bundle's lifecycle script, which takes a verified database backup, pauses the scheduled checks, switches the program folder, waits for one successful run of every enabled check plus a clean `rackmarshal doctor`, and rolls back by itself if that fails. It handles only 1.3.x to 1.3.y releases. If the new release adds database changes (always added after the newest one you already have, never altering earlier ones), the script rehearses them again on the backup, proves the program you are leaving still runs on the changed database (a full synthetic suite and a read-only check against a copy of your real data), runs the changes in one all-or-nothing step after the switch, and refuses anything that would lose data. Going back restores the old program and keeps the changed database and every newer record; it never rewinds your data. Releases that rewrite or remove earlier database changes are refused.

**This has not been qualified on a real machine and is not a supported upgrade path. Do not use `--apply` on a system you depend on.** The plan form (without `--apply`) is read-only.

## Why there is no in-place upgrade

RackMarshal 1.0.0 and 1.1.0 RC1 can record a pool that is online but reports permanent data errors as a counter change that opens no incident, and can close an open incident for that pool as recovered. They also record a missing error count as zero. Equal database schemas do not make it safe to carry that history forward unchanged, so the 1.3 tooling does not accept stable 1.0.0 as a starting point.

If you run 1.0.0 or 1.1.0 RC1 today, check `zpool status -v` by hand for permanent errors until you have moved to 1.3.

## The lifecycle script in the bundle

The installer bundle contains `scripts/lifecycle.py`. It is internal qualification tooling for 1.3.x to 1.3.y changes: the predecessor wheel must be supplied with its checksum (`--previous-sha256`), and releases that change units, rewrite earlier database changes or use custom layouts are refused. Appended database changes are supported only as described under `rackmarshal upgrade`. It has not been qualified on a real machine, is not an upgrade or rollback path for any release, and the install instructions do not use it. See [Private lifecycle qualification](docs/development/PRIVATE_LIFECYCLE_QUALIFICATION.md) if you want the details.
