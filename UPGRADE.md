# Upgrading RackMarshal

**RackMarshal 1.3 has no in-place upgrade.** The 1.3 installer installs fresh only and refuses to run when any RackMarshal directory, service account or systemd unit already exists. Do not delete preserved state to get around that check.

## Moving from 1.0.0 or 1.1.0 RC1

Install 1.3 on a new machine or container beside the old one, carry the configuration and credentials over, and start with a new history. Your old installation keeps its own history; leave it in place until you are satisfied with the new one. A step-by-step move guide will be published before the 1.3.0 final release.

## Why there is no in-place upgrade

RackMarshal 1.0.0 and 1.1.0 RC1 can record a pool that is online but reports permanent data errors as a counter change that opens no incident, and can close an open incident for that pool as recovered. They also record a missing error count as zero. Equal database schemas do not make it safe to carry that history forward unchanged, so the 1.3 tooling does not accept stable 1.0.0 as a starting point.

If you run 1.0.0 or 1.1.0 RC1 today, check `zpool status -v` by hand for permanent errors until you have moved to 1.3.

## The lifecycle script in the bundle

The installer bundle contains `scripts/lifecycle.py`. It is internal qualification tooling that supports only one exact chain between two private development builds. It is not an upgrade or rollback path for any release, and the install instructions do not use it. See [Private lifecycle qualification](docs/development/PRIVATE_LIFECYCLE_QUALIFICATION.md) if you want the details.
