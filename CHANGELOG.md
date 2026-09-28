# Changelog

All notable RackMarshal changes intended for public releases will be documented here.

RackMarshal has not yet published a stable release.

## [Unreleased]

### Added
- RackMarshal package structure extracted into a site-independent staging tree.
- SQLite schema construction through 12 ordered migrations.
- Domain manifests and processing components for PVE, ZFS, backup/PBS, Home Assistant, hardware, and mount monitoring.
- Local status API with `/health` and `/status` endpoints.
- Notification queue/service and timer packaging.
- Apache License 2.0 repository and package metadata.
- Debian/systemd reference installer and uninstall/purge workflow.
- Public installation, configuration, upgrade, uninstall, security, and contribution documentation.

### Verified during pre-release engineering
- fresh database construction from packaged migrations
- package import and plugin-entrypoint validation
- installation from built artifacts on a disposable clean Debian 12 host
- unprivileged service account and filesystem permissions
- systemd startup and health verification
- idempotent reinstall and migration preservation
- reboot recovery
- standard uninstall preserving configuration/state
- reinstall using preserved state
- destructive purge path
- whole-release publication/security scanning

### Changed
- remaining legacy project identifiers in staged Python and migration content were renamed for RackMarshal.

No GitHub release has been declared by this changelog entry.
