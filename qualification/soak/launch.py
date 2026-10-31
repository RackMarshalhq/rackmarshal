#!/usr/bin/env python3
"""Start a 24-hour soak of an INSTALLED RackMarshal on a disposable container.

Run it exactly like this (nothing else is accepted):

    umask 077
    python3 -I -B launch.py --target-hostname NAME --source-commit SHA [--launch]

Without --launch it only prints a preflight report and changes nothing. With
--launch it copies this kit to /opt/rackmarshal-soak, writes a pinned
config, installs a systemd timer (every 5 minutes, not enabled at boot), takes
the first sample immediately and only then starts the timer. If anything fails
it stops what it started and leaves STOP.json behind; it never retries.

The target must be a container you made for this purpose: it must carry a
root-owned marker file naming its own hostname, and RackMarshal must already be
installed from the release bundle with scripts/install.sh.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import time

# Isolated mode (-I) does not put the script's directory on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks
import driver
from common import canonical, clock, fsync_directory, load, require, save, sha256

UNIT = "rmq-soak"
MARKER = Path("/etc/rackmarshal-soak-target")
KIT_FILES = ("common.py", "checks.py", "fixture_cycles.py", "sample.py", "driver.py", "failure.py")
SYSTEMCTL = "/usr/bin/systemctl"


def invocation_problems(isolated, no_bytecode, umask, euid, platform, version):
    problems = []
    if not isolated:
        problems.append("run with python3 -I (isolated mode)")
    if not no_bytecode:
        problems.append("run with python3 -B (no bytecode: it would be written into the evidence)")
    if umask != 0o077:
        problems.append("run `umask 077` first (current umask is %04o)" % umask)
    if euid != 0:
        problems.append("run as root")
    if platform != "linux" or version < (3, 11):
        problems.append("needs Linux and Python 3.11 or newer")
    return problems


def target_problems(hostname_argument, hostname, marker=MARKER, owner_uid=0):
    """The marker proves a person made this machine disposable on purpose."""
    problems = []
    if hostname_argument != hostname:
        problems.append("--target-hostname %r does not match this machine (%r)" % (hostname_argument, hostname))
    try:
        info = marker.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid or info.st_mode & 0o022:
            problems.append("%s must be a root-owned file that others cannot write" % marker)
        elif marker.read_text().strip() != hostname:
            problems.append("%s does not contain this machine's hostname" % marker)
    except FileNotFoundError:
        problems.append("%s is missing; create it with the hostname of the disposable container" % marker)
    return problems


def kit_problems(kit):
    present = sorted(p.name for p in Path(kit).iterdir() if p.name != "launch.py" and p.name != "__pycache__")
    problems = []
    if present != sorted(KIT_FILES):
        problems.append("kit files differ from the expected set: %s" % present)
    if (Path(kit) / "__pycache__").exists():
        problems.append("kit contains __pycache__; run with python3 -B")
    return problems


def install_problems(venv, state_db, snapshot_dir, run):
    problems = []
    if not (Path(venv) / "bin" / "python").exists():
        problems.append("RackMarshal is not installed at %s" % venv)
        return problems
    code, output = run([SYSTEMCTL, "is-system-running"])
    if output.strip() != "running":
        problems.append("systemd reports %r, not 'running'" % output.strip())
    if not Path(state_db).is_file():
        problems.append("%s is missing" % state_db)
    if not Path(snapshot_dir).is_dir():
        problems.append("%s is missing: the install-time snapshot did not run" % snapshot_dir)
    return problems


def existing_problems(paths):
    problems = []
    for path in paths:
        try:
            exists = Path(path).exists()
        except OSError as error:  # for example PermissionError when not root
            problems.append("cannot inspect %s: %s" % (path, error.strerror or error))
            continue
        if exists:
            problems.append("%s already exists: a soak is never resumed, reset or overwritten" % path)
    return problems


def source_commit_problems(source_commit):
    return [] if re.fullmatch(r"[0-9a-f]{40}", source_commit) else ["--source-commit must be 40 lowercase hex characters"]


def space_problems(path, minimum):
    free = os.statvfs(path).f_bavail * os.statvfs(path).f_frsize
    return [] if free >= minimum else ["only %d bytes free under %s" % (free, path)]


def unit_texts(work, kit, gid):
    service = """[Unit]
Description=RackMarshal soak sample (disposable container)
ConditionPathExists=!{work}/STOP.json
ConditionPathExists=!{work}/COMPLETE.json

[Service]
Type=oneshot
User=rackmarshal
Group={gid}
SupplementaryGroups=systemd-journal
UMask=0077
WorkingDirectory={work}
ExecStart=/usr/bin/python3 -I -B -S {kit}/driver.py {work}
ExecStopPost=/usr/bin/python3 -I -B -S {kit}/failure.py {work}
TimeoutStartSec=290
TimeoutStopSec=15
KillMode=control-group
SendSIGKILL=yes
PrivateTmp=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths={work}
IPAddressDeny=any
IPAddressAllow=localhost
MemoryMax=768M
TasksMax=64
CPUQuota=100%
LimitFSIZE=16777216
""".format(work=work, kit=kit, gid=gid)
    timer = """[Unit]
Description=Five-minute RackMarshal soak sample

[Timer]
OnUnitActiveSec=300s
OnActiveSec=300s
AccuracySec=1s
RandomizedDelaySec=0
Persistent=false
Unit=%s.service
""" % UNIT
    return service, timer


def installed_site(venv):
    sites = list(Path(venv).glob("lib/python*/site-packages"))
    require(len(sites) == 1, "ambiguous site-packages")
    return sites[0]


def build_config(*, source_commit, venv, state_db, snapshot_dir, kit_hashes, boot_id, hostname, run):
    site = installed_site(venv)
    package = site / "rackmarshal"
    with closing(sqlite3.connect("file:%s?mode=ro" % state_db, uri=True)) as db:
        migrations = sorted(row[0] for row in db.execute("SELECT id FROM schema_migrations"))
    on_disk = [p for p in (package / "db" / "migrations").glob("*.sql")]
    require(len(migrations) == len(on_disk), "applied migrations (%d) differ from installed files (%d)"
            % (len(migrations), len(on_disk)))
    code, version = run([str(Path(venv) / "bin" / "python"), "-I", "-B", "-c",
                         "import rackmarshal;print(rackmarshal.__version__)"])
    return {"source_commit": source_commit, "hostname": hostname, "boot_id": boot_id,
            "venv": str(venv), "state_db": str(state_db), "snapshot_dir": str(snapshot_dir),
            "package_version": version.strip(), "package_hashes": checks.hash_package(package),
            "migrations": migrations, "kit_hashes": kit_hashes, "launched_utc_ns": time.time_ns(),
            "window_hours": 24, "cadence_seconds": 300, "max_gap_seconds": 420}


def copy_kit(source, destination, files=KIT_FILES):
    destination = Path(destination)
    destination.mkdir(mode=0o755)
    hashes = {}
    for name in files:
        data = (Path(source) / name).read_bytes()
        target = destination / name
        with target.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        target.chmod(0o444)
        hashes[name] = sha256(data)
    destination.chmod(0o555)
    fsync_directory(destination)
    return hashes


def run_command(argv, timeout=60):
    done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    return done.returncode, done.stdout


def launch(*, kit, source_commit, hostname, venv, state_db, snapshot_dir, kit_dest, work, unit_dir, launch_dir,
           owner, boot_id, run=run_command):
    """Do everything. Returns the report. On failure stops what it started and re-raises."""
    uid, gid = owner
    save(launch_dir / "LAUNCH-INTENT.json", {"at": clock(), "source_commit": source_commit})
    started = []
    try:
        kit_hashes = copy_kit(kit, kit_dest)
        config = build_config(source_commit=source_commit, venv=venv, state_db=state_db, snapshot_dir=snapshot_dir,
                              kit_hashes=kit_hashes, boot_id=boot_id, hostname=hostname, run=run)
        work.mkdir(mode=0o700)
        os.chown(work, uid, gid)
        for name in ("samples", "receipts"):
            (work / name).mkdir(mode=0o700)
            os.chown(work / name, uid, gid)
        save(work / "config.json", config)
        os.chown(work / "config.json", uid, gid)
        (work / "config.json").chmod(0o400)
        fsync_directory(work)
        service, timer = unit_texts(work, kit_dest, gid)
        for suffix, text in ((".service", service), (".timer", timer)):
            path = unit_dir / (UNIT + suffix)
            with path.open("x") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            path.chmod(0o644)
        save(launch_dir / "OWNED-UNITS.json", {unit: sha256((unit_dir / unit).read_bytes())
                                                 for unit in (UNIT + ".service", UNIT + ".timer")})
        require(run([SYSTEMCTL, "daemon-reload"])[0] == 0, "daemon-reload failed")
        started.append(UNIT + ".service")
        # The first sample runs now, in the foreground. The timer starts only after it passed.
        code, _ = run([SYSTEMCTL, "start", UNIT + ".service"], timeout=300)
        require(code == 0 and not (work / "STOP.json").exists(), "first sample failed")
        first = load(work / "receipts" / "00000000.json")
        require(first["result"] == "PASS", "first receipt missing")
        driver.validate_chain(work, load(work / "config.json"))
        started.append(UNIT + ".timer")
        require(run([SYSTEMCTL, "start", UNIT + ".timer"])[0] == 0, "timer did not start")
        require(run([SYSTEMCTL, "is-active", UNIT + ".timer"])[1].strip() == "active", "timer not active")
    except BaseException as error:
        for unit in reversed(started):
            run([SYSTEMCTL, "stop", unit], timeout=40)
        if work.exists() and not (work / "STOP.json").exists():
            save(work / "STOP.json", {"result": "FAIL_STOP", "reason": "launch incomplete", "error": repr(error),
                                      "at": clock()})
        raise
    report = {"result": "SOAK_STARTED", "source_commit": source_commit, "package_version": config["package_version"],
              "config_sha256": sha256(canonical(config)), "first_receipt_sha256": sha256(canonical(first)),
              "first_start": first["start"], "work": str(work), "completion": "PENDING",
              "enabled_on_boot": False,
              "read_result": "after about 24 h: %s/COMPLETE.json exists and the chain validates; STOP.json means failed" % work}
    save(launch_dir / "LAUNCHED.json", report)
    return report


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-hostname", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--launch", action="store_true", help="really start the soak (default: preflight only)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    kit = Path(__file__).resolve().parent
    venv, state_db = Path("/opt/rackmarshal/venv"), Path("/var/lib/rackmarshal/state.db")
    snapshot_dir = state_db.parent / "db-snapshots"
    kit_dest, work = Path("/opt/rackmarshal-soak"), Path("/var/lib/rackmarshal-soak")
    launch_dir = Path("/root/soak-launch")
    unit_dir = Path("/etc/systemd/system")
    problems = []
    problems += invocation_problems(sys.flags.isolated, sys.dont_write_bytecode, os.umask(0o077),
                                    os.geteuid(), sys.platform, sys.version_info[:2])
    problems += target_problems(args.target_hostname, socket.gethostname())
    problems += source_commit_problems(args.source_commit)
    problems += kit_problems(kit)
    problems += install_problems(venv, state_db, snapshot_dir, run_command)
    problems += existing_problems([kit_dest, work, launch_dir / "LAUNCH-INTENT.json",
                                   unit_dir / (UNIT + ".service"), unit_dir / (UNIT + ".timer")])
    if not problems:
        problems += space_problems("/var/lib", 2 * 2**30)
    if problems:
        print("PREFLIGHT_FAILED")
        for problem in problems:
            print("  - " + problem)
        return 2
    print("PREFLIGHT_OK")
    if not args.launch:
        print("Nothing was changed. Add --launch to start the soak.")
        return 0
    launch_dir.mkdir(mode=0o700, exist_ok=True)
    account = pwd.getpwnam("rackmarshal")
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    report = launch(kit=kit, source_commit=args.source_commit, hostname=args.target_hostname, venv=venv,
                    state_db=state_db, snapshot_dir=snapshot_dir, kit_dest=kit_dest, work=work, unit_dir=unit_dir,
                    launch_dir=launch_dir, owner=(account.pw_uid, account.pw_gid), boot_id=boot_id)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
