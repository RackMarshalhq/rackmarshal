# RackMarshal™

**Know when your homelab is actually unhealthy, and when it has recovered.**

RackMarshal watches your Proxmox, ZFS, Home Assistant, hardware and mounts, keeps a local history in SQLite, and opens one incident per real problem instead of a pile of repeat alerts. An incident closes only when RackMarshal records evidence of recovery. It runs on your own hardware and does not send data to any cloud service.

## Who it is for

- You run Proxmox, ZFS or Home Assistant at home or in a small lab.
- You have been bitten by a pool that went DEGRADED, a mount that vanished, or a backup that quietly stopped.
- You want a short, trustworthy "what is wrong right now" page rather than another wall of graphs.

## What you get

- A status page and read-only API, served on `127.0.0.1:9110` by default (local only).
- Incidents with evidence, a timeline and a recovery check.
- Notifications through Home Assistant, queued with retry.
- A SQLite history you own, copied daily to a local snapshot folder.

## Try it

1. **Install** on a fresh Debian 12 or Ubuntu machine with systemd (a small LXC container is fine): [INSTALL.md](INSTALL.md).
2. **Confirm the base install:** `curl http://127.0.0.1:9110/health` returns HTTP 200 and the status page at `http://127.0.0.1:9110/` shows no incidents.
3. **Add one thing to watch.** Follow the [quickstart](docs/QUICKSTART.md).

A fresh install with nothing enabled should show no incidents. If it shows one, that is a bug. Please [open an issue](../../issues/new/choose).

## Status

| Release | State |
|---|---|
| 1.0.0 | Stable, but see the ZFS note below |
| 1.1.0 RC1 | Tester preview, same ZFS note |
| 1.3.0 | Release candidate, in qualification. Looking for outside testers: [TESTING.md](TESTING.md) |

**ZFS note for 1.0.0 and 1.1.0 RC1:** a pool that is ONLINE but reports permanent data errors is recorded as a counter change, opens no incident, and can close an open incident as recovered. A missing error count is recorded as zero. 1.3 fixes this. If you run an earlier release on ZFS, check `zpool status -v` yourself.

1.2 was never released; 1.3 includes its work. For anything beyond trying it out, install from a tagged release rather than from a development branch.

## What it does not do

- It does not repair anything. It observes, records and reports.
- It is not a metrics or graphing tool. Run Grafana alongside it if you want graphs.
- It does not discover your infrastructure. You choose what it watches, and a base install watches nothing.
- Monitoring a domain requires site configuration, credentials and a baseline that says what healthy looks like. The installer never copies or invents them.
- In 1.3 the backup domain is not supported for new installations (it has no baseline tool yet). See [CONFIGURATION.md](CONFIGURATION.md).
- There is no in-place upgrade in 1.3. See [UPGRADE.md](UPGRADE.md).

## Safety

Collectors only read: Proxmox uses an API token you create, and ZFS, hardware and mount checks use SSH keys that you restrict to a single fixed command on the target. The service runs as an unprivileged `rackmarshal` account and the status API listens on loopback unless you change it. See [SECURITY.md](SECURITY.md) and [CONFIGURATION.md](CONFIGURATION.md).

## Documentation

[Quickstart](docs/QUICKSTART.md) · [Install](INSTALL.md) · [Configure](CONFIGURATION.md) · [Upgrade](UPGRADE.md) · [Uninstall](UNINSTALL.md) · [Architecture](docs/architecture/README.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [Testing](TESTING.md) · [Soak test](SOAK.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).

Website: https://rackmarshal.com · Source: https://github.com/RackMarshalhq/rackmarshal

RackMarshal™ is an independent project and is not affiliated with Proxmox Server Solutions GmbH.
