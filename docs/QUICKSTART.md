# Quickstart: watch one thing

This takes a fresh base install ([INSTALL.md](INSTALL.md)) to a first real observation. Pick **one** domain. ZFS is the simplest to try if you have a pool; Home Assistant is the simplest if you have a long-lived access token.

Before you start, check the base install:

```bash
systemctl is-active rackmarshal-status.service rackmarshal-notify.timer
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9110/health   # expect 200
```

Open `http://127.0.0.1:9110/` (from the same machine, or through an SSH tunnel). You should see no incidents.

## Rules that apply to every domain

- Edit `/etc/rackmarshal/rackmarshal.conf` as root.
- Check your work with `sudo rackmarshal validate-config --config /etc/rackmarshal/rackmarshal.conf` and `sudo rackmarshal setup-plan --config /etc/rackmarshal/rackmarshal.conf`. `setup-plan` shows missing key *names* only, never values, and changes nothing.
- Credentials live in separate files under `/etc/rackmarshal`, readable by the `rackmarshal` account and nobody else. Never commit them.
- After setting `ENABLED_DOMAINS`, rerun the installer (see [CONFIGURATION.md](CONFIGURATION.md)). It enables one timer per domain.

## Option A: ZFS

RackMarshal connects over SSH and runs `zpool status -j -p`. The safe setup is a dedicated key on the ZFS host that can run only that one command.

1. On RackMarshal's machine, make a key: `sudo -u rackmarshal ssh-keygen -t ed25519 -N '' -f /etc/rackmarshal/ssh/zfs_ed25519` (create the directory first, owned by `rackmarshal`, mode 0700).
2. On the ZFS host, create a user (for example `rackmarshal-observer`) and add the public key to its `authorized_keys` with a forced command:

   ```text
   command="/usr/sbin/zpool status -j -p",restrict ssh-ed25519 AAAA... rackmarshal
   ```

   RackMarshal passes no command of its own, so the forced command is what runs.
3. Record the host key: `ssh-keyscan -t ed25519 your-zfs-host > /etc/rackmarshal/ssh/known_hosts`. Check the fingerprint yourself. RackMarshal always uses strict host-key checking.
4. In `rackmarshal.conf`:

   ```text
   ENABLED_DOMAINS=zfs
   ZFS_SSH_HOST=your-zfs-host
   ZFS_SSH_USER=rackmarshal-observer
   ZFS_SSH_KEY=/etc/rackmarshal/ssh/zfs_ed25519
   ZFS_KNOWN_HOSTS=/etc/rackmarshal/ssh/known_hosts
   ```
5. Validate, rerun the installer, then run one cycle now instead of waiting for the timer:

   ```bash
   sudo systemctl start rackmarshal-domain@zfs.service
   journalctl -u rackmarshal-domain@zfs.service -n 30 --no-pager
   ```

**You should now see:** the ZFS domain on the status page with a recent observation and no incident (assuming your pool is healthy).

## Option B: Home Assistant (also enables notifications)

1. In Home Assistant, create a long-lived access token (profile page).
2. Create `/etc/rackmarshal/home-assistant-api.env`, owned by root, group `rackmarshal`, mode 0640:

   ```text
   HA_URL=http://your-home-assistant:8123
   HA_TOKEN=your-token
   ```
3. Set `ENABLED_DOMAINS=ha` in `rackmarshal.conf`, validate, and rerun the installer.
4. Run one cycle: `sudo systemctl start rackmarshal-domain@ha.service`.

Other domains (Proxmox, PBS, hardware, mounts) need more keys. [CONFIGURATION.md](CONFIGURATION.md) lists them, and `setup-plan` tells you which ones are still missing.

## Troubleshooting

| Symptom | Check |
|---|---|
| Status service will not start | `journalctl -u rackmarshal-status.service -n 50 --no-pager`; confirm port 9110 is free. |
| `curl` to `/health` is refused | `systemctl status rackmarshal-status.service`; confirm `STATUS_API_LISTEN_ADDRESS` and `STATUS_API_LISTEN_PORT`. |
| `validate-config` fails | Run `setup-plan`; it names the missing keys and unreadable credential files. |
| No data after 10 minutes | `systemctl list-timers 'rackmarshal-*'`; confirm `ENABLED_DOMAINS` is set and the installer was rerun. |
| ZFS cycle fails with an SSH error | Test the key by hand: `sudo -u rackmarshal ssh -i /etc/rackmarshal/ssh/zfs_ed25519 -o UserKnownHostsFile=/etc/rackmarshal/ssh/known_hosts user@host`. It should print `zpool` JSON and exit. |
| An incident appears on the first run | That may be real. Read its evidence on the status page. If your system is healthy, please report it with the Bug report template. |

Stuck anywhere? That is useful to us. See [TESTING.md](TESTING.md).
