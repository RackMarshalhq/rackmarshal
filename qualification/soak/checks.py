"""Install-layer checks: does the INSTALLED product still look and behave as installed?

Each check returns a small dict that always carries "result": "PASS" and raises
ValueError on any failure. Anything that touches the machine (systemctl,
journalctl, HTTP, the clock) is passed in, so the checks are unit-testable.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import urllib.request

from common import require, sha256

EXPECTED_ACTIVE = {
    "rackmarshal-status.service": "active",
    "rackmarshal-notify.timer": "active",
    "rackmarshal-db-snapshot.timer": "active",
}
STATUS_URL = "http://127.0.0.1:9110"
SNAPSHOT_FILE = re.compile(r"state\.db\.\d{8}-\d{6}(?:-\d{6})?Z")
SNAPSHOT_MAX_AGE_SECONDS = 26 * 3600
MINIMUM_FREE_BYTES = 256 * 2**20


def hash_package(package_dir):
    """sha256 of every file in the installed package, ignoring bytecode caches."""
    package_dir = Path(package_dir)
    result = {}
    for path in sorted(package_dir.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        require(not path.is_symlink(), "link in installed package: %s" % path)
        if path.is_file():
            result[str(path.relative_to(package_dir))] = sha256(path.read_bytes())
    return result


def installed_files(package_dir, pinned):
    actual = hash_package(package_dir)
    missing = sorted(set(pinned) - set(actual))
    extra = sorted(set(actual) - set(pinned))
    changed = sorted(name for name in set(actual) & set(pinned) if actual[name] != pinned[name])
    require(not (missing or extra or changed),
            "installed package differs: missing=%s extra=%s changed=%s" % (missing[:3], extra[:3], changed[:3]))
    return {"result": "PASS", "files": len(actual)}


def run_command(argv, timeout=15):
    done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    return done.returncode, done.stdout


def units(run=run_command):
    seen = {}
    for unit, wanted in EXPECTED_ACTIVE.items():
        code, output = run(["/usr/bin/systemctl", "show", unit, "-p", "ActiveState", "-p", "NRestarts"])
        fields = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        require(code == 0 and fields.get("ActiveState") == wanted, "%s is not %s" % (unit, wanted))
        seen[unit] = fields
    code, output = run(["/usr/bin/systemctl", "--failed", "--plain", "--no-legend", "--no-pager"])
    failed = [line.split()[0] for line in output.splitlines() if line.strip()]
    require(code == 0 and not failed, "failed units: %s" % failed)
    # A service that restarts in a loop still reports "active"; count restarts.
    require(int(seen["rackmarshal-status.service"].get("NRestarts", "0")) == 0, "status service restarted")
    return {"result": "PASS", "units": seen}


def http_get(path):
    with urllib.request.urlopen(STATUS_URL + path, timeout=10) as response:
        return response.status, json.loads(response.read(2**20))


def status_api(get=http_get):
    seen = {}
    for path in ("/health", "/status", "/v1/health", "/v1/status", "/v1/domains"):
        code, body = get(path)
        require(code == 200 and isinstance(body, dict), "%s returned %s" % (path, code))
        seen[path] = code
    require(get("/v1/health")[1].get("api_version") == "v1", "API version differs")
    return {"result": "PASS", "paths": seen}


def database(path, expected_migrations):
    uri = "file:%s?mode=ro" % path
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
        require(connection.execute("PRAGMA quick_check").fetchone()[0] == "ok", "live database quick_check failed")
        applied = {row[0] for row in connection.execute("SELECT id FROM schema_migrations")}
    require(applied == set(expected_migrations), "applied migrations differ from the installed set")
    return {"result": "PASS", "migrations": len(applied), "bytes": os.stat(path).st_size}


def snapshots(directory, now=None):
    directory = Path(directory)
    now = now if now is not None else time.time()
    files = sorted(p for p in directory.iterdir() if SNAPSHOT_FILE.fullmatch(p.name) and p.is_file())
    require(files, "no database snapshot exists")
    newest = files[-1]
    age = now - newest.stat().st_mtime
    require(age <= SNAPSHOT_MAX_AGE_SECONDS, "newest snapshot is %d s old" % age)
    with closing(sqlite3.connect("file:%s?mode=ro" % newest, uri=True, timeout=10)) as connection:
        require(connection.execute("PRAGMA quick_check").fetchone()[0] == "ok", "snapshot quick_check failed")
    require((directory / "state.db.latest").is_file(), "state.db.latest is missing")
    require(len(files) <= 8, "retention not applied: %d snapshots" % len(files))
    return {"result": "PASS", "snapshots": len(files), "newest_age_seconds": int(age)}


def journal_errors(since, run=run_command):
    """Error-level (or worse) log lines from RackMarshal units since the previous sample."""
    code, output = run(["/usr/bin/journalctl", "--no-pager", "-q", "-p", "err", "-o", "cat",
                        "--since", since, "-u", "rackmarshal-*"], timeout=20)
    lines = [line for line in output.splitlines() if line.strip()]
    require(code == 0, "journalctl failed")
    require(not lines, "error log lines since %s: %s" % (since, lines[:3]))
    return {"result": "PASS"}


def resources(state_dir, run=run_command):
    free = os.statvfs(state_dir)
    available = free.f_bavail * free.f_frsize
    require(available >= MINIMUM_FREE_BYTES, "only %d bytes free" % available)
    code, output = run(["/usr/bin/systemctl", "show", "rackmarshal-status.service", "-p", "MainPID", "-p", "MemoryCurrent"])
    fields = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    return {"result": "PASS", "free_bytes": available, "status_service": fields}
