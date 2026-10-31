# Become a RackMarshal tester

We are looking for **5 to 10 people** to try the 1.3 release candidate on a real setup and tell us honestly what confused or broke.

**You need:** a fresh Debian 12 or Ubuntu machine or container with systemd, about 30 minutes, and at least one of Proxmox, ZFS or Home Assistant to watch.

**What we ask:**
1. Install it ([INSTALL.md](INSTALL.md)). Note how long it took and where you got stuck.
2. Check that a fresh install shows no incidents.
3. Add one thing to watch ([quickstart](docs/QUICKSTART.md)).
4. Use it for a week or two.
5. Tell us what happened using the **Tester feedback** issue template.

**What we promise:** collection is read-only, nothing is sent to a cloud service, uninstalling is documented ([UNINSTALL.md](UNINSTALL.md)), and we aim to reply to every report within 48 hours.

**What we are not asking for:** code, money, or a public review. A report that says "I got stuck at step 3" is exactly what we need.

Maintainers preparing a release also run a 24-hour soak test: [SOAK.md](SOAK.md).
