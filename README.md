# RackMarshal™

Local-first infrastructure operations and incident management for self-hosted systems.

RackMarshal observes infrastructure, records durable operational state, detects and tracks incidents, and verifies recovery. It grew from a working homelab operations system and is now available for broader use across homelabs, self-hosted infrastructure, edge systems, and small infrastructure environments.

> **Project status:** RackMarshal 1.1.0 RC1 is a tester preview. RackMarshal 1.0.0 remains the stable release.

## 1.1.0 RC1 tester preview

[Download 1.1.0 RC1](https://github.com/RackMarshalhq/rackmarshal/releases/tag/v1.1.0-rc1) for the incident dashboard, versioned read APIs, eleven read-only MCP tools, recorded provenance and lifecycle evidence, and portable Investigator policy. **1.0.0 remains the stable release.**

The release includes SHA256SUMS and a sanitized qualification summary. Exact-artifact checks cover fresh Debian 12 installation/reboot, stable upgrade/rollback/reupgrade, state/configuration preservation, and MCP protocol boundaries. CI passes on Python 3.11–3.13. See the summary for security findings and qualification limits.

Read the [tagged changelog](https://github.com/RackMarshalhq/rackmarshal/blob/v1.1.0-rc1/CHANGELOG.md), [upgrade guide](https://github.com/RackMarshalhq/rackmarshal/blob/v1.1.0-rc1/UPGRADE.md), and [hosted Investigator setup](https://github.com/RackMarshalhq/rackmarshal/blob/v1.1.0-rc1/docs/architecture/HOSTED_INVESTIGATOR_SETUP.md). Hosted use requires a private connection binding; private workspace configuration and operational records are excluded from public assets. Local plugin client installation and implicit activation are not qualified.

## What exists today

The current codebase contains operational domains for:

- Proxmox VE resources
- ZFS storage health
- backup/PBS observations
- Home Assistant observations
- hardware health
- mount availability

RackMarshal stores observations, events, incidents, cycle health, and related state in SQLite. Domain manifests describe the available collector/processing entrypoints, and the local status API exposes `/health` and `/status`.

## Design principles

- Local-first operation
- Durable operational history
- Evidence-based incident detection and recovery
- Configuration-driven monitoring
- Reproducible installation and database migration
- Minimal dependence on external services
- Designed for infrastructure you control

## Installation

The reference installer currently targets Debian/Ubuntu-compatible systems using systemd and Python 3.11 or newer. It creates a dedicated unprivileged `rackmarshal` account, installs the wheel into `/opt/rackmarshal/venv`, creates the configuration/state directories, applies database migrations, installs systemd units, and verifies the local health endpoint.

See [INSTALL.md](INSTALL.md) before installing. Configuration details are in [CONFIGURATION.md](CONFIGURATION.md).

## Important current boundary

A successful base installation proves the RackMarshal runtime, database, status API, and notification queue can run. It does **not** automatically configure access to your Proxmox, PBS, Home Assistant, ZFS, hardware, or mount targets. Those integrations require site-specific configuration and credentials.

The installer does not copy production credentials or discover your infrastructure automatically.

## Documentation

- [Architecture and agent roadmap](docs/architecture/README.md)
- [Installation](INSTALL.md)
- [Configuration](CONFIGURATION.md)
- [Upgrade](UPGRADE.md)
- [Uninstall](UNINSTALL.md)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

RackMarshal is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

## Project links

Website: https://rackmarshal.com  
Source: https://github.com/RackMarshalhq/rackmarshal

RackMarshal™ is an independent project and is not affiliated with Proxmox Server Solutions GmbH.
