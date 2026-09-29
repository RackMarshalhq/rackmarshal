# Changelog

## 1.0.0

- Added the supported `rackmarshal` CLI with version, domain listing, configuration validation, migration, and diagnostic commands.
- Added explicit enabled-domain scheduling with generic hardened systemd service/timer templates.
- Added automated unit, comparator, notification failure, installer-contract, migration, smoke, and publication gates.
- Added GitHub Actions CI, CodeQL, Dependabot, and reproducible release-build workflow.
- Added deterministic installer-bundle construction and strengthened preflight validation.


All notable RackMarshal changes intended for public releases will be documented here.

RackMarshal 1.0.0 is the first stable public release.

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

The pre-release engineering record above documents the qualification work that led to the 1.0.0 release.
