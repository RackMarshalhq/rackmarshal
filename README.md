# RackMarshal™

**Development: 1.2.0.dev1.** Setup/coverage improvements are under qualification; published RC1 remains a separate artifact.

Local-first infrastructure operations and incident management for self-hosted systems.

RackMarshal observes infrastructure, records durable operational state, detects and tracks incidents, and verifies recovery. It grew from a working homelab operations system and is now available for broader use across homelabs, self-hosted infrastructure, edge systems, and small infrastructure environments.

> **Project status:** RackMarshal 1.1.0 RC1 is a tester preview. RackMarshal 1.0.0 remains the stable release.

## What exists today

The current codebase contains operational domains for:

- Proxmox VE resources
- ZFS storage health
- backup/PBS observations
- Home Assistant observations
- hardware health
- mount availability

RackMarshal stores observations, events, incidents, cycle health, and related state in SQLite. Domain manifests describe the available collector/processing entrypoints, and the local status API exposes `/health`, `/status`, and the read-only versioned `/v1` API. The incident dashboard, lifecycle/evidence views, and optional eleven-tool MCP Investigator build on recorded state.

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
