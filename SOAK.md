# Soak test: run an installed RackMarshal for 24 hours

A soak test installs RackMarshal on a throwaway container, leaves it running, and checks it every
five minutes for 24 hours. It answers one question: does the installed product stay healthy, or does
it drift, leak, restart or log errors when nobody is touching it?

It is for people preparing a release. You do not need it to use RackMarshal.

## What each sample checks

Every five minutes, one sample records a pass or fail for each of these:

| Check | What it proves |
| --- | --- |
| `installed_files` | Every installed file is byte-identical to what was installed at the start |
| `units` | The status service and the notify and snapshot timers are active, nothing has failed, and the status service has not restarted |
| `status_api` | The local status API answers `/health`, `/status`, `/v1/health`, `/v1/status`, `/v1/domains` |
| `database` | The live database passes SQLite's integrity check and still has exactly the installed migrations |
| `snapshots` | A database snapshot less than 26 hours old exists, opens, passes its own integrity check, and retention is applied |
| `journal_errors` | No RackMarshal unit logged an error since the previous sample |
| `resources` | At least 256 MiB of disk is free; service memory is recorded |
| `fixture_cycles` | Nine synthetic ZFS cycles (healthy, degraded, persistent errors, unknown, replaced pool, recovery) and seven invalid inputs give the exact expected answers, run in a sandbox that cannot reach the network or the real database |

A sample passes only if every check passes. Each sample is a receipt that contains the hash of the
receipt before it, so a missing, edited or reordered sample is detected.

## What it does not prove

* It uses synthetic data. It does not talk to a real Proxmox host, ZFS pool, Home Assistant or
  backup server, so it does not test your collectors against real hardware.
* The optional MCP server, tunnel and local-AI explainer are not part of the base install and are
  not tested here.
* The backup domain is not supported for new installations in 1.3 and is not exercised.
* A pass means "this build stayed healthy for 24 hours on that container". It is not a security audit.

## Before you start

1. Make a disposable container (or VM) that you are happy to delete. Debian 12 or newer, Python 3.11 or newer.
2. Install RackMarshal from the release bundle with `scripts/install.sh`, following `INSTALL.md`.
   Leave the default settings. Do not enable any domain.
3. Tell the machine it is disposable, on purpose, by writing its own hostname into a marker file:

       hostname > /etc/rackmarshal-soak-target
       chmod 644 /etc/rackmarshal-soak-target

4. Copy the folder `qualification/soak/` from the exact commit you are testing onto the machine.
   Note the full 40-character commit id.

## Start it

    umask 077
    cd qualification/soak
    python3 -I -B launch.py --target-hostname "$(hostname)" --source-commit <40-character commit id>

That is a **preflight only**. It prints `PREFLIGHT_OK`, or a list of what is wrong, and changes
nothing. It refuses, among other things, if it was not started with `-I -B` and `umask 077`, if you
are not root, if the hostname or marker does not match, if RackMarshal is not installed, or if a
soak was already started on this machine.

When the preflight is clean, run the same command with `--launch` added. It then takes the first
sample immediately, and only if that passes does it start the five-minute timer. The timer is not
enabled at boot: if the machine reboots, the soak stops, because a reboot would invalidate it.

Never restart, resize, snapshot-restore or reboot the container during the 24 hours.

## Read the result

Everything is under `/var/lib/rackmarshal-soak`:

* `COMPLETE.json` exists: the window finished. It needs at least 24 hours **and** 280 samples.
* `STOP.json` exists: the soak failed and will never run again. It says why. The failed sample is kept
  under `samples/` and `glitches/`; nothing is deleted.
* Neither exists: it is still running. Do not read elapsed time as a pass.

One failed sample is quarantined under `glitches/` and retried once. A second failure of the same
sample, or a third glitch in the window, stops the soak. If a stop happens, make a new container;
a stopped soak is never resumed or reset.

## Run the tests for the kit itself

    python3 -m unittest tests.test_soak
